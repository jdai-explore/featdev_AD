# Functional Safety & SOTIF Safety Goals Specification
**Feature:** `FEAT-L3-HWY-CHAUFFEUR`  
**Standards:** ISO 26262:2018 (Part 3), ISO 21448:2022 (Clause 8), ISO/PAS 8800:2024  

---

### 1. Functional Safety Goals (ISO 26262)
* **SG-LAT-01 (ASIL D):** Prevent unintended lateral steering torque command exceeding 3.0 Nm.
  * **FTTI:** $\le 20\text{ ms}$.
  * **Safe State:** Transition lateral control to secondary AURIX TC4x lockstep MCU within 20ms or disengage with audible warning.
* **SG-LAT-02 (ASIL D):** Prevent unannounced total loss of steering assistance during highway curve navigation.
  * **FTTI:** $\le 50\text{ ms}$.
  * **Safe State:** Execute Minimum Risk Maneuver (MRM) trajectory to highway shoulder.
* **SG-LONG-03 (ASIL C):** Inhibit false positive emergency braking exceeding $2.0\text{ m/s}^2$ without multi-sensor confirmation.
  * **FTTI:** $\le 100\text{ ms}$.

---

### 2. SOTIF Triggering Condition Mitigations (ISO 21448)
* **SG-SOTIF-01:** Under low sun elevation ($< 5^\circ$), fuse camera with 4D imaging radar and HD map corridor to prevent loss of lane tracking.
* **SG-SOTIF-02:** Issue advisory TOR Stage 1 at least 10.0 seconds prior to known construction zone boundaries.
