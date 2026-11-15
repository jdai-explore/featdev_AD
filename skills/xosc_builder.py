"""
Skill: ASAM OpenSCENARIO Programmatic Generator & Kinematic Feasibility Verifier
Powered by the official 'scenariogeneration' Python library.
Synthesizes schema-compliant ASAM OpenSCENARIO 1.2 XML files for CARLA, esmini, and openPASS.
Performs kinematic physics checks (deceleration limits, lateral acceleration envelopes, TTC bounds).
"""

import sys
import json
import math
import datetime
from pathlib import Path
from typing import Dict, Any

from scenariogeneration import xosc, prettyprint

def verify_kinematic_feasibility(
    ego_speed_mps: float,
    target_speed_mps: float,
    ttc_trigger_s: float,
    lane_change_duration_s: float,
    lane_width_m: float = 3.5
) -> Dict[str, Any]:
    """
    Validates that the scenario does not violate physical vehicle dynamics
    (ISO 21448 SOTIF physical plausibility criteria).
    """
    violations = []
    
    # 1. Lateral acceleration envelope during lane change
    # Assuming sinusoidal transition: a_lat_peak = (2 * pi * lane_width) / (duration^2)
    a_lat_peak = (2.0 * math.pi * lane_width_m) / (lane_change_duration_s ** 2)
    if a_lat_peak > 4.5:
        violations.append(
            f"Unrealistic lateral acceleration: peak a_lat = {a_lat_peak:.2f} m/s^2 exceeds passenger vehicle limit (4.5 m/s^2)"
        )

    # 2. Closing speed and minimum deceleration required
    rel_speed_mps = ego_speed_mps - target_speed_mps
    if rel_speed_mps > 0:
        clearance_m = rel_speed_mps * ttc_trigger_s
        # Braking deceleration required to avoid collision: a = v_rel^2 / (2 * clearance)
        a_brake_req = (rel_speed_mps ** 2) / (2.0 * max(clearance_m, 1.0))
        if a_brake_req > 6.0:
            violations.append(
                f"Physically impossible deceleration required: a_req = {a_brake_req:.2f} m/s^2 exceeds maximum road friction limit (6.0 m/s^2)"
            )

    # 3. TTC safety thresholds
    if ttc_trigger_s < 0.8:
        violations.append(
            f"TTC trigger {ttc_trigger_s:.2f}s is below emergency reaction threshold (0.8s) causing guaranteed crash"
        )

    return {
        "kinematically_feasible": len(violations) == 0,
        "peak_lateral_accel_mps2": round(a_lat_peak, 2),
        "violations": violations
    }

def generate_openscenario(params: Dict[str, Any], output_path: Path) -> Dict[str, Any]:
    scenario_id = params.get("scenario_id", "SCENARIO_CUTIN_DEFAULT")
    desc = params.get("description", "Deterministic SOTIF Evaluation Scenario")
    opendrive_map = params.get("opendrive_map", "../maps/autobahn_a9_3lane.xodr")
    ego_speed_mps = float(params.get("ego_speed_mps", 36.11)) # 130 km/h
    target_speed_mps = float(params.get("target_speed_mps", ego_speed_mps * 0.85)) # 85% of ego speed
    ttc_trigger_s = float(params.get("ttc_trigger_s", 2.2))
    seed = int(params.get("rng_seed", 42))
    lc_duration_s = float(params.get("lane_change_duration_s", 2.5))
    sun_elev = float(params.get("sun_elevation_deg", 4.5))
    rain_intensity = float(params.get("precipitation_intensity", 0.5))

    # Kinematic Sanity Verification
    kinematics = verify_kinematic_feasibility(ego_speed_mps, target_speed_mps, ttc_trigger_s, lc_duration_s)
    if not kinematics["kinematically_feasible"]:
        return {
            "status": "FAIL",
            "stage": "KINEMATIC_FEASIBILITY",
            "errors": kinematics["violations"]
        }

    # Parameter Declarations (Locked seeds & reproducible inputs per OpenSCENARIO 1.2)
    param_decl = xosc.ParameterDeclarations()
    param_decl.add_parameter(xosc.Parameter("EgoSpeed_mps", xosc.ParameterType.double, str(ego_speed_mps)))
    param_decl.add_parameter(xosc.Parameter("TargetSpeed_mps", xosc.ParameterType.double, str(target_speed_mps)))
    param_decl.add_parameter(xosc.Parameter("CARLA_RNG_Seed", xosc.ParameterType.int, str(seed)))

    # Entities Setup
    entities = xosc.Entities()
    entities.add_scenario_object("Ego_Vehicle", xosc.CatalogReference("VehicleCatalog", "Sedan_L3_SensorSuite"))
    entities.add_scenario_object("CutIn_Target", xosc.CatalogReference("VehicleCatalog", "Truck_40t"))

    # Road Network
    road = xosc.RoadNetwork(opendrive_map)
    catalogs = xosc.Catalog()

    # Storyboard Initialization
    init = xosc.Init()

    # Ego initial speed
    ego_speed_action = xosc.AbsoluteSpeedAction(
        "$EgoSpeed_mps",
        xosc.TransitionDynamics(xosc.DynamicsShapes.step, xosc.DynamicsDimension.time, 0.0)
    )
    init.add_init_action("Ego_Vehicle", ego_speed_action)

    # Target initial speed
    target_speed_action = xosc.AbsoluteSpeedAction(
        "$TargetSpeed_mps",
        xosc.TransitionDynamics(xosc.DynamicsShapes.step, xosc.DynamicsDimension.time, 0.0)
    )
    init.add_init_action("CutIn_Target", target_speed_action)

    # Global Environment Action (SOTIF low-sun glare + precipitation, OSC 1.2 compliant)
    weather = xosc.Weather(
        cloudstate=xosc.FractionalCloudCover.eightOktas,
        sun=xosc.Sun(intensity=15000.0, azimuth=3.14, elevation=sun_elev),
        precipitation=xosc.Precipitation(xosc.PrecipitationType.rain, intensity=rain_intensity)
    )
    env = xosc.Environment("SOTIF_Adverse_Conditions", weather=weather)
    init.add_global_action(xosc.EnvironmentAction(env))

    # Story & Act Construction
    story = xosc.Story("SOTIF_CutIn_Story")
    act = xosc.Act("Aggressive_CutIn_Act")
    mgroup = xosc.ManeuverGroup("CutInGroup", maxexecution=1)
    mgroup.add_actor("CutIn_Target")

    maneuver = xosc.Maneuver("CutInManeuver")
    event = xosc.Event("StartCutIn", priority=xosc.Priority.override)

    # Cut-In Lane Change Action
    lc_dynamics = xosc.TransitionDynamics(xosc.DynamicsShapes.sinusoidal, xosc.DynamicsDimension.time, lc_duration_s)
    lc_action = xosc.RelativeLaneChangeAction(0, "Ego_Vehicle", lc_dynamics)
    event.add_action("CutInLaneChange", lc_action)

    # TTC Trigger Condition
    ttc_cond = xosc.TimeToCollisionCondition(
        value=ttc_trigger_s,
        freespace=True,
        rule=xosc.Rule.lessThan,
        entity="Ego_Vehicle"
    )
    trigger = xosc.EntityTrigger("TTC_Threshold_Met", 0.0, xosc.ConditionEdge.rising, ttc_cond, "CutIn_Target")
    event.add_trigger(trigger)

    maneuver.add_event(event)
    mgroup.add_maneuver(maneuver)
    act.add_maneuver_group(mgroup)
    story.add_act(act)

    storyboard = xosc.StoryBoard(init)
    storyboard.add_story(story)

    # Create full Scenario using scenariogeneration with fixed deterministic creation date
    scenario = xosc.Scenario(
        name=scenario_id,
        author="Agent_07_Scenario_Sim_Orch",
        parameters=param_decl,
        entities=entities,
        storyboard=storyboard,
        roadnetwork=road,
        catalog=catalogs,
        osc_minor_version=2,
        creation_date=datetime.datetime(2026, 11, 15, 0, 0, 0)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    scenario.write_xml(str(output_path))

    return {
        "status": "PASS",
        "engine": "scenariogeneration.xosc (Official ASAM OpenSCENARIO Library)",
        "output_file": str(output_path),
        "scenario_id": scenario_id,
        "ego_speed_mps": ego_speed_mps,
        "target_speed_mps": target_speed_mps,
        "ttc_trigger_s": ttc_trigger_s,
        "peak_lateral_accel_mps2": kinematics["peak_lateral_accel_mps2"],
        "rng_seed": seed
    }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: xosc_builder.py <params_json> <output_xosc>"}))
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        params_in = json.load(f)

    res = generate_openscenario(params_in, Path(sys.argv[2]))
    print(json.dumps(res, indent=2))
    if res["status"] != "PASS":
        sys.exit(2)
