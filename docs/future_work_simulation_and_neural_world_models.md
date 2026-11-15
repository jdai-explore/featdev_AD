# Future Work: Live Simulation Engines & Neural World Models Integration
**Document Ref:** `DOC-FW-SIM-001`  
**Target Systems:** CARLA Simulator, esmini Headless Runner, NVIDIA Cosmos / NIM, ASAM OSI & FMI/FMU  

---

## 1. Executive Summary & Purpose

The current ADAS/AD agentic engineering framework programmatically generates and verifies schema-valid **ASAM OpenSCENARIO 1.2 (`.xosc`)** and **OpenDRIVE (`.xodr`)** files with deterministic parameter locks (e.g. `CARLA_RNG_Seed = 42`) and kinematic physics feasibility assertions. 

This document parks the architectural roadmap for connecting these generated files to **live execution engines** across four simulation and world-model tiers.

---

## 2. Target Integration Tiers

```mermaid
flowchart TD
    subgraph FrameworkArtifacts ["Generated Framework Artifacts"]
        XOSC["ASAM OpenSCENARIO (.xosc)"]
        XODR["ASAM OpenDRIVE (.xodr)"]
        CTRL["MISRA-C Controller (.c / FMU)"]
    end

    subgraph Tier1 ["Tier 1: Fast Headless Logic (CI/CD)"]
        ESMINI["esmini CLI Runner (CPU, <200ms)"]
    end

    subgraph Tier2 ["Tier 2: 3D Physics & Multi-Sensor Sim"]
        CARLA["CARLA 0.9.15 / UE5 (Synchronous Mode)"]
        SR["CARLA ScenarioRunner"]
    end

    subgraph Tier3 ["Tier 3: Generative Neural SOTIF"]
        COSMOS["NVIDIA Cosmos Foundation Models (NIM APIs)"]
        OMNI["NVIDIA Omniverse NuRec / Isaac Sim"]
    end

    subgraph Tier4 ["Tier 4: Co-Simulation & Telemetry"]
        OSI["ASAM OSI (Open Simulation Interface)"]
        MCAP["Foxglove MCAP Telemetry Auditing"]
    end

    XOSC & XODR --> Tier1
    XOSC & XODR --> Tier2
    CARLA -->|Spatial Conditioning (Depth/Layout)| Tier3
    CTRL & CARLA --> Tier4
```

---

## 3. Tier 1: Headless Fast Simulation via `esmini`

### Goal:
Execute generated scenarios headlessly in continuous integration (CI/CD) pipelines on CPU-only runners without requiring GPU hardware or game engine rendering.

### Technical Scope:
1. **Skill Module:** `skills/esmini_runner.py`
2. **Execution Wrapper:**
   ```bash
   esmini --window 0 0 800 600 --headless --fixed_timestep 0.01 --osc <scenario.xosc> --record <telemetry.csv>
   ```
3. **Automated KPI Assertion:**
   - Evaluates vehicle trajectory, lateral error, and collision status in $< 200\text{ ms}$.
   - Evaluates Transition of Control (TOR) timing budgets before submitting to the Gatekeeper.

---

## 4. Tier 2: Live Full-Stack 3D Simulation via CARLA Simulator

### Goal:
Execute closed-loop perception, sensor fusion, and vehicle chassis dynamics inside an Unreal Engine photorealistic 3D environment.

### Technical Scope:
1. **Skill Module:** `skills/carla_runner.py`
2. **CARLA Python API Client (`carla.Client`):**
   - Connects to `localhost:2000` (or remote cluster).
   - Enforces **Synchronous Mode**:
     ```python
     settings = world.get_settings()
     settings.synchronous_mode = True
     settings.fixed_delta_seconds = 0.01  # Exact 100 Hz physics tick
     world.apply_settings(settings)
     ```
   - Spawns ego vehicle equipped with sensor suites defined in `artifacts/06_vehicle_arch_icd.json` (8MP cameras, 4D radars, LiDAR).
3. **ScenarioRunner Integration:**
   - Ingests the `.xosc` files produced by `Agent 07 (Scenario & Sim Orchestrator)`.
   - Records binary replayer logs (`.log`) and telemetry streams for bit-for-bit replayability.

---

## 5. Tier 3: Neural World Models via NVIDIA Cosmos & NIM APIs

### Goal:
Overcome the "sim-to-real gap" and render real-world visual edge cases mandated by **ISO 21448 (SOTIF)** that synthetic game-engine shaders struggle to produce accurately (e.g., blinding low morning sun glare on wet asphalt, 40-ton truck aerosol spray plumes, lens smudge, and faded road construction markings).

### Technical Scope:
1. **Skill Module:** `skills/cosmos_client.py`
2. **Architecture:**
   - Traditional render engines (CARLA / Unreal) output clean ground-truth layouts: depth maps, semantic segmentation, and 3D bounding boxes.
   - These spatial conditioning inputs are piped via REST/gRPC to **NVIDIA Cosmos** foundation world models:
     * **Cosmos-Predict / Cosmos-Transfer:** Conditioned diffusion generation that transforms CARLA synthetic frames into photorealistic multi-camera video streams.
     * **NVIDIA NIM (Inference Microservice):** Cloud or on-prem containerized inference endpoints with fixed seeds.
3. **Closed-Loop SOTIF Evaluation:**
   - The generated photorealistic camera stream is fed back into the perception model (e.g. `SwinTransformer_LaneNet_V4`) to test if lane boundaries are dropped under extreme sun glare or spray.

---

## 6. Tier 4: Co-Simulation & Standard Interfaces (ASAM OSI & FMI/FMU)

### Goal:
Decouple vehicle dynamics, control models, and simulation engines using vendor-neutral standards.

### Technical Scope:
1. **ASAM Open Simulation Interface (OSI):**
   - Standardizes sensor data (OSI SensorData) and ground-truth obstacles (OSI GroundTruth) using Google Protocol Buffers (`.proto`).
   - Enables hot-swapping between esmini, CARLA, and real-world test-bench replay without modifying the control code wrappers.
2. **FMI / FMU (Functional Mock-up Interface):**
   - Packages `artifacts/08_lane_controller.c` into an FMU (Functional Mock-up Unit) with fixed-step numerical solvers for integration into hardware-in-the-loop (HiL) dyno benches.
3. **Foxglove MCAP Telemetry Logging:**
   - Generates standardized `.mcap` container logs for recording all in-vehicle bus traffic (CAN-FD, Ethernet TSN) during simulation runs.

---

## 7. Implementation Checklist for Future Activation

- [ ] Install `esmini` binary on CI runner host and configure `ESMINI_HOME` environment variable.
- [ ] Deploy CARLA 0.9.15 server instance on local GPU workstation or cloud test container.
- [ ] Secure NVIDIA NIM API credentials for NVIDIA Cosmos foundation models.
- [ ] Author `skills/carla_runner.py` and `skills/esmini_runner.py`.
- [ ] Connect simulation telemetry parsers to `Agent 08 (MBD & Telemetry Verification)`.
