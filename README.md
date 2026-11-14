# Autonomous Driving & ADAS Feature Engineering Agentic Framework

A deterministic, multi-agent engineering platform for designing, verifying, and validating safety-critical Advanced Driver Assistance Systems (ADAS) and Autonomous Driving (AD) features from SAE Level 2 through Level 4.

## Key Capabilities & Pillars
- **Feature-Agnostic Core:** Governs L2+ Hands-Off/Eyes-On (UN R171 DCAS), L3 Highway Chauffeur (UN R157 ALKS), and L4 Automated Valet Parking / Shuttles (German StVG / AFGBV) via declarative configuration profiles.
- **Human-in-the-Loop Hub-and-Spoke Governance:** Eliminates autonomous agent runaway. Agents produce verifiable, version-controlled diffs gated by automated linters before human sign-off.
- **Strict Bit-for-Bit Determinism:** Zero LLM temperature, pinned model checkpoints, fixed RNG seeds, content-addressable SHA-256 context hashing, and sandboxed VCR tool recording/replaying.
- **Bi-Directional Relational Traceability:** Embedded SQLite graph (`kg5_traceability.sqlite`) linking regulations $\to$ ODD $\to$ HMI $\to$ Safety Goals (ASIL/FTTI) $\to$ E/E ICD $\to$ Scenarios $\to$ Code $\to$ Test KPIs.
- **Pre-Review Gatekeeper Linters:** Zero agent output reaches human review unless JSON/YAML/XSD schemas, MISRA-C rules, and state machine completeness pass 100%.

## Architecture Overview
```mermaid
flowchart TD
    subgraph HumanCoordinator ["Human Coordinator (The Hub)"]
        HC["Engineering Lead Review & Sign-Off"]
    end

    subgraph DeterministicRuntime ["Deterministic Core (.determinism/)"]
        MLOCK["Model & Inference Lock (temp=0.0, seed=424242)"]
        VCR["Tool Call VCR Cache (Sandboxed Replay)"]
        AUDIT["Execution Bundle Cryptographic Audit Trail"]
    end

    subgraph KnowledgeGraphs ["5 Shared Knowledge Graphs"]
        KG1["KG1: Regulatory & Compliance (UN R157/R171, ISO 26262/21448/8800)"]
        KG2["KG2: ASAM OpenODD & Roadway Taxonomy"]
        KG3["KG3: E/E Platform, Compute & Sensor Suite"]
        KG4["KG4: Hazard, SOTIF Triggers & AI Failure Modes"]
        KG5["KG5: Bi-Directional Relational Traceability (SQLite)"]
    end

    subgraph AgentSwarm ["11 Specialized Engineering Agents"]
        A01["01: Regulatory & Homologation"]
        A02["02: ODD Architect (OpenODD 1.0)"]
        A03["03: Feature Activation & Cybersecurity (UN R155/R156)"]
        A04["04: Human Factors & HMI (ToC / TOR / MRM)"]
        A05["05: Safety, SOTIF & AI Safety (HARA / ASIL D)"]
        A06["06: System & E/E Architect (Dual-Compute ICD)"]
        A07["07: Scenario & Sim Orchestrator (OpenSCENARIO)"]
        A08["08: MBD & Verification (MISRA-C & KPIs)"]
        A09["09: ML/AI Safety Tuning (ISO/PAS 8800)"]
        A10["10: HW/SW Integration (WCET & Latency)"]
        A11["11: Change Request Impact Analyzer"]
    end

    subgraph GatekeeperLayer ["Automated Pre-Review Gatekeeper"]
        GK["Pre-Review Gatekeeper (Schemas, State Machines, MISRA-C, Traceability)"]
    end

    HC -->|Invokes with Pinned Context| AgentSwarm
    AgentSwarm -->|Queries| KnowledgeGraphs
    AgentSwarm -->|Runs Sandboxed Skills| DeterministicRuntime
    AgentSwarm -->|Emits Artifacts & Bundles| GK
    GK -->|Pass 100%| HC
    GK -->|Fail| AgentSwarm
    A11 -.->|Traverses Ripple Effects| KG5
```

## Quick Start & Usage
### 1. Run Framework Verification Suite
```powershell
python tests/test_framework.py
```

### 2. List Registered Agents
```powershell
python orchestrator/pipeline_runner.py list-agents
```

### 3. Execute an Agent Phase (e.g. HMI Design)
```powershell
python orchestrator/pipeline_runner.py run-agent --agent-id AGENT_04_HUMAN_FACTORS_HMI --feature-id FEAT-L3-HWY-CHAUFFEUR
```

### 4. Human Coordinator Cryptographic Sign-Off
```powershell
python orchestrator/pipeline_runner.py signoff --agent-id AGENT_04_HUMAN_FACTORS_HMI --feature-id FEAT-L3-HWY-CHAUFFEUR
```

### 5. Trigger Change Request Ripple Analysis
```powershell
python orchestrator/pipeline_runner.py trigger-change --trace-id ODD-SPEC-001 --reason "Lowered minimum visibility threshold to 120m"
```
