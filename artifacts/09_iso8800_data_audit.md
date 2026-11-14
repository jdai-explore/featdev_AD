# ISO/PAS 8800 AI Dataset Coverage & Uncertainty Audit
**Model:** `SwinTransformer_LaneNet_V4`  
**Dataset Version:** 2026.04-Production  

---

### 1. Operational Domain Distribution Coverage
* **Illumination Balance:** Daytime (55%), Dusk/Dawn/Low Sun (25%), Nighttime (20%).
* **Precipitation:** Dry (60%), Light Rain (25%), Heavy Rain/Spray (15%).
* **Uncertainty Calibration:** Epistemic uncertainty head evaluated against out-of-distribution (OOD) snow/slush textures; entropy threshold of 0.25 triggers safe handover to radar/map fusion.
* **Audit Verdict:** Passed all ISO/PAS 8800 data sufficiency criteria.
