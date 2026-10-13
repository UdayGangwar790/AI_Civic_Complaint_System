# M3.8 — Priority / Risk Intelligence

## 1. Objective
The objective of Module 3.8 is to compute a transparent, explainable civic triage priority score (0–100) and assign an actionable civic priority level (`P1`, `P2`, `P3`, `P4`) for complaint triage.

The system is explicitly designed as a municipal decision-support tool. It does **not** predict medical emergencies, guarantee physical danger, or infer priority based on citizen identity or protected demographic attributes.

## 2. Explainable Scoring Model & Formula
Priority is determined through an explainable linear additive model with an upper bound normalized to 100:

$$\text{Raw Priority Score} = S_{\text{base\_issue}} + S_{\text{text\_risk}} + S_{\text{repeat}} + S_{\text{location}} + S_{\text{confidence}}$$

$$\text{Priority Score} = \min(100, \max(0, \text{Raw Priority Score}))$$

Where the individual component scores are calculated from available evidence:
1. **$S_{\text{base\_issue}}$ (Base Civic Issue Score)**:
   - `open_damaged_manhole`: 50
   - `road_waterlogging`: 35
   - `damaged_missing_road_sign`: 25
   - `other_civic_issue` / unknown: 20
2. **$S_{\text{text\_risk}}$ (Textual Risk & Severity Signal Contribution)**:
   - Proportional to detected NLP severity keywords (`dangerous`, `accident`, `injury`, `deep/open`, `blocked road`, `night visibility issue`, `emergency-like wording`) and safety risk signals (`fall hazard`, `electrocution`, etc.).
   - Scaled by `PRIORITY_WEIGHT_TEXT_RISK` (default: 20).
3. **$S_{\text{repeat}}$ (Duplicate / Repeat Occurrence Evidence)**:
   - If classified as `duplicate`: `PRIORITY_WEIGHT_REPEAT` (default: 15).
   - If classified as `possible_duplicate`: `0.5 \times \text{PRIORITY_WEIGHT_REPEAT}` (7.5).
   - If unique or no duplicate data: 0.
4. **$S_{\text{location}}$ (Location / Highway / Critical Context)**:
   - Elevated if detected on major arterial corridors (National Highway `NH`, State Highway `SH`, Ring Road, Bypass) or critical civic infrastructure: `PRIORITY_WEIGHT_LOCATION` (default: 10).
5. **$S_{\text{confidence}}$ (Computer Vision Evidence Strength)**:
   - Proportional to YOLO detection confidence ($C_{cv} \in [0, 1]$), scaled by `PRIORITY_WEIGHT_CONFIDENCE` (default: 5).
   - Evaluates **evidence strength**, not physical severity.

## 3. Configurable Weights & Thresholds
All parameters are defined in `backend/app/core/config.py`:
```python
PRIORITY_BASE_SCORES = {
    "open_damaged_manhole": 50,
    "road_waterlogging": 35,
    "damaged_missing_road_sign": 25,
    "other_civic_issue": 20,
}
PRIORITY_WEIGHT_TEXT_RISK = 20
PRIORITY_WEIGHT_REPEAT = 15
PRIORITY_WEIGHT_LOCATION = 10
PRIORITY_WEIGHT_CONFIDENCE = 5

PRIORITY_P1_THRESHOLD = 80  # P1 — Critical (score >= 80)
PRIORITY_P2_THRESHOLD = 60  # P2 — High (score >= 60)
PRIORITY_P3_THRESHOLD = 40  # P3 — Medium (score >= 40)
# Below 40 is P4 — Low
```

## 4. Priority Levels & Risk Semantics
- **`P1` — Critical (`>= 80`)**: Severe civic hazard requiring urgent municipal dispatch (e.g., open manhole on high-speed road with repeated reports and pedestrian fall hazard signals). Risk level: `Critical Safety Hazard`.
- **`P2` — High (`60–79`)**: Elevated civic risk (e.g., deep waterlogging on arterial road, or open manhole with baseline evidence). Risk level: `High Civic Concern`.
- **`P3` — Medium (`40–59`)**: Moderate civic disruption (e.g., damaged road sign on arterial road, or localized waterlogging). Risk level: `Moderate Civic Disruption`.
- **`P4` — Low (`< 40`)**: Minor or localized non-hazardous issue. Risk level: `Low Civic Impact`.

## 5. Non-Fabricated Evidence & Reasons Generation
Every score includes an explicit breakdown of the factual evidence and human-readable reasons that contributed to the rating:
```json
{
  "priority_score": 83,
  "priority_level": "P1",
  "risk_level": "Critical Safety Hazard",
  "reasons": [
    "Base civic issue category 'open_damaged_manhole' has high inherent public safety impact (+50).",
    "NLP analysis detected urgent safety risk signals: fall hazard, pedestrian vulnerability (+15).",
    "Repeated/duplicate citizen reports indicate persistent unresolved condition (+15).",
    "High-confidence computer vision detection confirms physical evidence (+3)."
  ],
  "evidence": [
    "Civic class: open_damaged_manhole",
    "CV detection confidence: 0.89",
    "Detected severity signals: dangerous, deep/open, injury",
    "Duplicate status: duplicate"
  ],
  "limitations": [
    "Priority scoring is an explainable engineering baseline and is not a scientifically validated emergency prediction model.",
    "CV confidence indicates detection likelihood, not severity of physical danger.",
    "Text risk signals represent reported wording and do not confirm physical injuries."
  ]
}
```

## 6. Protection of Citizen Attributes & Ethical Boundaries
- **No Protected Attributes**: The algorithm accepts only civic issue type, computer vision confidence, NLP text signals, duplicate history, and location infrastructure. Citizen names, phone numbers, demographic identities, and user IDs are strictly excluded from the scoring model.
- **Authority Independence**: Authority verification status determines routing readiness, not intrinsic physical hazard score.

## 7. Disclaimers & Known Limitations
> [!IMPORTANT]
> **Priority scoring is an explainable engineering baseline and is not a scientifically validated emergency prediction model.**

- **Decision-Support Only**: The output assists municipal complaint sorting and triage. It must not be treated as a medical emergency dispatch system.
- **Evidence Strength Distinction**: A 95% YOLO confidence score denotes high model certainty regarding object presence, not 95% danger.

## 8. Verification & Test Suite
Module 3.8 is validated by `backend/tests/test_priority_m38.py` covering:
1. Low-risk minor complaint produces P4 rating.
2. High-risk open manhole with text danger signals correctly scales to P1.
3. Severe waterlogging with risk indicators produces P2/P1 rating.
4. Road sign issue evaluates to standard baseline priority.
5. Repeat complaint duplicate signal elevates priority score.
6. Resilient handling when duplicate information is omitted.
7. Low CV confidence adjustment behavior.
8. High CV confidence adjustment behavior.
9. Resilient operation when location context is missing.
10. Resilient operation when authority context is missing.
11. Guarantee that priority score is strictly bounded in $[0, 100]$.
12. Exact validation of P1, P2, P3, P4 threshold mapping.
13. Audit verifying reasons correspond strictly to actual provided inputs without hallucination.
14. Strict verification that protected personal attributes are never accepted or used.
15. Resilient handling of malformed input payloads.
