# Worst-Case Execution Time (WCET) & Latency Budget Report
**Compute Platforms:** NVIDIA DRIVE Thor + Infineon AURIX TC4x  
**Safety Timing:** FTTI $\le 20\text{ ms}$ for Steering, $\le 50\text{ ms}$ for Braking  

---

### 1. End-to-End Pipeline Latency Breakdown
* Camera Exposure & Readout: $12.5\text{ ms}$
* Preprocessing & NPU Neural Inference: $18.0\text{ ms}$
* Sensor Fusion & Multi-Object Tracking: $6.5\text{ ms}$
* Motion Planning & Trajectory Synthesis: $5.0\text{ ms}$
* CAN-FD / TSN Transmission Delay: $1.8\text{ ms}$
* **Total Sensor-to-Actuator Latency:** **$43.8\text{ ms}$** (Budget: $45.0\text{ ms}$ $\rightarrow$ **PASS**)
* **Failover MCU Watchdog Reaction Time:** **$14.2\text{ ms}$** (Budget: $20.0\text{ ms}$ $\rightarrow$ **PASS**)
