# System & E/E Architecture Document
**Feature:** `FEAT-L3-HWY-CHAUFFEUR`  
**ASIL Target:** ASIL D Fail-Operational Architecture  

---

### 1. Dual-Compute Fail-Operational Allocation
* **Primary AD Domain Controller (ECU_PRIMARY_AD):**
  * Hardware: NVIDIA DRIVE Thor (Blackwell GPU + NPU + ARM Neoverse V3AE).
  * Role: Multi-camera/LiDAR/Radar perception, world model prediction, dynamic trajectory planning.
  * WCET Budget: $45.0\text{ ms}$.
* **Safety Supervisor & Fallback MCU (ECU_SAFETY_FAILOVER):**
  * Hardware: Infineon AURIX TC4x (Hexa-core TriCore with Safety Lockstep Core).
  * Role: Independent trajectory plausibility verification, heartbeat watchdog, MRM execution, and DSSAD logging.
  * Failover Switch Latency: $\le 20.0\text{ ms}$.

---

### 2. Network Topology & Redundancy
* **Sensors:** 8x 8MP Cameras (GMSL2), 5x Radars (4D Imaging via Ethernet TSN, corners via CAN-FD), 1x Solid-State LiDAR (TSN).
* **Power Supply:** Isolated dual-rail power distribution (KL30A and KL30B).
* **Actuation:** Dual-winding Electric Power Steering (EPS) and dual-redundant OneBox brake controller.
