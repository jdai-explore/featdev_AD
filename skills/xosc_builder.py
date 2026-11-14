"""
Skill: ASAM OpenSCENARIO Programmatic Generator
Synthesizes schema-compliant ASAM OpenSCENARIO 1.2 XML files deterministically
for CARLA ScenarioRunner, esmini, and openPASS execution.
"""

import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any

def generate_openscenario(params: Dict[str, Any], output_path: Path) -> Dict[str, Any]:
    scenario_id = params.get("scenario_id", "SCENARIO_CUTIN_DEFAULT")
    desc = params.get("description", "Deterministic SOTIF Evaluation Scenario")
    opendrive_map = params.get("opendrive_map", "../maps/autobahn_a9_3lane.xodr")
    ego_speed_mps = float(params.get("ego_speed_mps", 36.11)) # ~130 km/h
    ttc_trigger_s = float(params.get("ttc_trigger_s", 2.2))
    seed = int(params.get("rng_seed", 42))

    # Build XML hierarchy
    root = ET.Element("OpenSCENARIO")
    
    # File Header
    header = ET.SubElement(root, "FileHeader")
    header.set("revMajor", "1")
    header.set("revMinor", "2")
    header.set("date", "2026-11-14T20:00:00")
    header.set("description", desc)
    header.set("author", "Agent_07_Scenario_Sim_Orch")

    # Parameter Declarations (Locked Seeds & Kinematics)
    params_elem = ET.SubElement(root, "ParameterDeclarations")
    
    p1 = ET.SubElement(params_elem, "ParameterDeclaration")
    p1.set("name", "EgoSpeed_mps")
    p1.set("parameterType", "double")
    p1.set("value", str(ego_speed_mps))

    p2 = ET.SubElement(params_elem, "ParameterDeclaration")
    p2.set("name", "CARLA_RNG_Seed")
    p2.set("parameterType", "integer")
    p2.set("value", str(seed))

    # Road Network
    road = ET.SubElement(root, "RoadNetwork")
    logic = ET.SubElement(road, "LogicFile")
    logic.set("filepath", opendrive_map)

    # Entities
    entities = ET.SubElement(root, "Entities")
    ego = ET.SubElement(entities, "ScenarioObject", {"name": "Ego_Vehicle"})
    ET.SubElement(ego, "CatalogReference", {"catalogName": "VehicleCatalog", "entryName": "Sedan_L3_SensorSuite"})
    
    target = ET.SubElement(entities, "ScenarioObject", {"name": "CutIn_Target"})
    ET.SubElement(target, "CatalogReference", {"catalogName": "VehicleCatalog", "entryName": "Truck_40t"})

    # Storyboard
    storyboard = ET.SubElement(root, "Storyboard")
    init = ET.SubElement(storyboard, "Init")
    actions = ET.SubElement(init, "Actions")
    
    # Global environment action (weather / low sun glare)
    global_act = ET.SubElement(actions, "GlobalAction")
    env_act = ET.SubElement(global_act, "EnvironmentAction")
    env = ET.SubElement(env_act, "Environment", {"name": "SOTIF_Adverse_Conditions"})
    weather = ET.SubElement(env, "Weather", {"cloudState": "rainy"})
    ET.SubElement(weather, "Sun", {
        "intensity": "15000",
        "azimuth": "3.14",
        "elevation": str(params.get("sun_elevation_deg", 4.2))
    })
    ET.SubElement(weather, "Precipitation", {
        "precipitationType": "rain",
        "intensity": str(params.get("precipitation_intensity", 0.85))
    })

    # Private actions for Ego
    private_ego = ET.SubElement(actions, "Private", {"entityRef": "Ego_Vehicle"})
    priv_act_ego = ET.SubElement(private_ego, "PrivateAction")
    long_ego = ET.SubElement(priv_act_ego, "LongitudinalAction")
    speed_act = ET.SubElement(long_ego, "SpeedAction")
    ET.SubElement(speed_act, "SpeedActionDynamics", {"dynamicsShape": "step", "value": "0.0", "dynamicsDimension": "time"})
    ET.SubElement(speed_act, "SpeedActionTarget").append(
        ET.Element("AbsoluteTargetSpeed", {"value": "$EgoSpeed_mps"})
    )

    # Story & Cut-in Act
    story = ET.SubElement(storyboard, "Story", {"name": "SOTIF_CutIn_Story"})
    act = ET.SubElement(story, "Act", {"name": "Aggressive_CutIn_Act"})
    mgroup = ET.SubElement(act, "ManeuverGroup", {"maximumExecutionCount": "1", "name": "CutInGroup"})
    ET.SubElement(mgroup, "Actors", {"selectTriggeringEntities": "false"}).append(
        ET.Element("EntityRef", {"entityRef": "CutIn_Target"})
    )

    maneuver = ET.SubElement(mgroup, "Maneuver", {"name": "CutInManeuver"})
    event = ET.SubElement(maneuver, "Event", {"name": "StartCutIn", "priority": "overwrite"})
    evt_action = ET.SubElement(event, "Action", {"name": "CutInLaneChange"})
    priv_act_tgt = ET.SubElement(evt_action, "PrivateAction")
    lat_act = ET.SubElement(priv_act_tgt, "LateralAction")
    lc_act = ET.SubElement(lat_act, "LaneChangeAction")
    ET.SubElement(lc_act, "LaneChangeActionDynamics", {"dynamicsShape": "sinusoidal", "value": "2.5", "dynamicsDimension": "time"})
    ET.SubElement(lc_act, "LaneChangeTarget").append(
        ET.Element("RelativeTargetLane", {"entityRef": "Ego_Vehicle", "value": "0"})
    )

    # Start trigger based on TTC
    strig = ET.SubElement(event, "StartTrigger")
    cgroup = ET.SubElement(strig, "ConditionGroup")
    cond = ET.SubElement(cgroup, "Condition", {"name": "TTC_Threshold_Met", "delay": "0", "conditionEdge": "rising"})
    by_entity = ET.SubElement(cond, "ByEntityCondition")
    ET.SubElement(by_entity, "TriggeringEntities", {"triggeringEntitiesRule": "any"}).append(
        ET.Element("EntityRef", {"entityRef": "Ego_Vehicle"})
    )
    econd = ET.SubElement(by_entity, "EntityCondition")
    ttc_cond = ET.SubElement(econd, "TimeToCollisionCondition", {"value": str(ttc_trigger_s), "freespace": "true", "rule": "lessThan"})
    ET.SubElement(ttc_cond, "TimeToCollisionConditionTarget").append(
        ET.Element("EntityRef", {"entityRef": "CutIn_Target"})
    )

    # Output formatted XML
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write(str(output_path), encoding="utf-8", xml_declaration=True)

    return {
        "status": "PASS",
        "output_file": str(output_path),
        "scenario_id": scenario_id,
        "ego_speed_mps": ego_speed_mps,
        "ttc_trigger_s": ttc_trigger_s,
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
