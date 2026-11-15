# Tiered Virtual Simulation & Verification Plan
**Feature:** `FEAT-L3-HWY-CHAUFFEUR`  
**Engines:** esmini, CARLA 0.9.15, NVIDIA Cosmos  

---

### 1. Multi-Tier Verification Stack
1. **Tier 1 (Fast Kinematics & Logic):** esmini headless simulation. Validates state transitions, TOR timing, and MRM fallbacks in CI/CD pipeline within seconds.
2. **Tier 2 (Full 3D Sensor & Vehicle Physics):** CARLA Simulator in Synchronous Mode (`fixed_delta_seconds = 0.01`, Seed = 42). Tests closed-loop perception and control with realistic vehicle dynamics.
3. **Tier 3 (Neural World Models for SOTIF Edge Cases):** NVIDIA Cosmos / Omniverse NuRec. Generates high-fidelity photorealistic camera sensor sweeps (low morning sun glare, heavy truck aerosol spray, wet asphalt reflections).
