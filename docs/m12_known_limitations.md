# CVKI M12.7: Known Limitations & Technical Debt

This document candidly outlines the known architectural boundaries, environmental limitations, model constraints, and technical debt present in the CVKI v1 release baseline.

---

## 1. Computer Vision & Visual Detection Limitations

1. **Vocabulary Scope**:
   - The frozen model (`M1.13` YOLOv8n) is trained across a fixed 13-class civic taxonomy (`garbage`, `pothole`, `street_light_issue`, `water_leakage`, `fallen_tree`, `damaged_signboard`, `broken_bench`, `open_damaged_manhole`, `illegal_parking`, `sewage_overflow`, `encroachment`, `unauthorized_posters`, `loose_cables`). It cannot detect hazards outside this vocabulary.
2. **Dataset Scale & Bias**:
   - The baseline dataset contains exactly 605 annotated images. While curated for high precision, it exhibits daytime and clear-weather distribution bias. Detection accuracy degrades under low-light nighttime illumination, heavy precipitation, or extreme motion blur.
3. **No 3D / Depth Measurement**:
   - The detector outputs 2D bounding boxes. It cannot calculate metric pothole depth, waterlogging volume, or structural structural load-bearing degradation.
4. **No Video / Temporal Tracking**:
   - The model evaluates individual static photographic frames; temporal video stream tracking is omitted from the v1 release.

---

## 2. Multimodal & Vernacular NLP Limitations

1. **Deterministic Rule-Based Normalizer**:
   - CVKI deliberately eschews external non-deterministic Large Language Models (LLMs) to ensure epistemic safety and zero external data exfiltration. Consequently, vernacular translation relies on structured lexical rule tables. Highly localized slang, code-mixed dialects, or phonetic spelling variants may fail to normalize.
2. **Grammar & Semantics**:
   - Deep contextual sentiment or sarcastic intent is not analyzed. The normalizer targets entity extraction and category identification only.

---

## 3. Geospatial & Authority Resolution Boundaries

1. **Cadastral & Boundary Ambiguity**:
   - Authority resolution relies on OpenStreetMap (OSM) highway tags and official government registry databases. If cadastral data for a recently transferred or newly built road is missing, the resolver falls back to `not_verified` municipal defaults.
2. **Inter-Agency Border Disputes**:
   - Corridors where statutory maintenance has been disputed in court between state public works departments and municipal corporations cannot be autonomously resolved by CVKI and are flagged as conflicting.

---

## 4. Government Portal Integration Realities

1. **External API Availability**:
   - National and municipal grievance portals (e.g., CPGRAMS, state CM portals) frequently experience sandbox downtime, CAPTCHA changes, or undocumented schema changes. When external endpoints fail, CVKI records `UNKNOWN_OUTCOME` or `DISABLED` states.
2. **Asymmetric Redress Life Cycles**:
   - External government portals may mark a ticket as "Closed" administratively without physical site remediation. CVKI does not equate external administrative closure with physical ground truth.

---

## 5. Deployment & Infrastructure Boundaries

1. **Single-Node Local Baseline**:
   - The system is benchmarked as a local engineering baseline. It is not packaged with multi-region Kubernetes Helm charts or high-availability failover topologies.
2. **Cloud Deployment**:
   - Cloud deployment is not pre-configured out-of-the-box.
