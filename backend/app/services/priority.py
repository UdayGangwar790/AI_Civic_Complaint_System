from typing import Any, Optional
import re

from app.core.config import settings
from app.schemas.priority import (
    PriorityLevel,
    PriorityScoreRequest,
    PriorityScoreResponse,
    RiskLevel,
)
from app.schemas.civic_intelligence import RecurrenceAnalysis

MAJOR_CORRIDOR_KEYWORDS = [
    "highway", "expressway", "arterial", "flyover", "metro", "hospital",
    "school", "station", "main road", "ring road", "bypass", "marg", "chowk"
]


def calculate_priority_score(
    request: PriorityScoreRequest,
    recurrence_analysis: RecurrenceAnalysis | None = None,
) -> PriorityScoreResponse:
    """
    Computes a transparent, explainable civic priority score (0-100)
    for triage decision support based on available multi-modal signals.
    Does NOT use protected personal attributes or citizen identities.
    """
    reasons: list[str] = []
    evidence: list[str] = []

    # 1. Base Issue Score
    base_scores = settings.PRIORITY_BASE_SCORES
    base_score = base_scores.get(request.issue_category, base_scores.get("other_civic_issue", 20))

    if request.issue_category == "open_damaged_manhole":
        reasons.append("Open or damaged manhole presents an immediate physical fall hazard to pedestrians and vehicles.")
    elif request.issue_category == "road_waterlogging":
        reasons.append("Road waterlogging creates traffic obstruction, submerged hazard risks, and road erosion.")
    elif request.issue_category == "damaged_missing_road_sign":
        reasons.append("Damaged or missing road sign impairs driver navigation and regulatory traffic guidance.")
    else:
        reasons.append("Reported civic issue categorized under standard municipal maintenance triage.")

    evidence.append(f"Base hazard score for '{request.issue_category}': {base_score} pts")

    # 2. NLP Text Risk Score (up to PRIORITY_WEIGHT_TEXT_RISK = 20)
    text_risk_score = 0
    if request.nlp_analysis:
        nlp = request.nlp_analysis
        sev_signals = nlp.severity_signals or []
        risk_signals = nlp.risk_signals or []

        high_impact_signals = {"accident", "injury", "dangerous", "emergency-like wording", "deep/open"}
        mod_impact_signals = {
            "blocked road", "night visibility issue", "severe flooding",
            "repeated occurrence", "fall hazard", "vehicle damage risk"
        }

        matched_high = [s for s in sev_signals if s in high_impact_signals]
        matched_mod = [s for s in (sev_signals + risk_signals) if s in mod_impact_signals]

        pts = (len(matched_high) * 10) + (len(matched_mod) * 5)
        text_risk_score = min(settings.PRIORITY_WEIGHT_TEXT_RISK, pts)

        if text_risk_score > 0:
            found_signals = list(dict.fromkeys(matched_high + matched_mod))
            reasons.append(f"High-urgency risk signals detected in complaint text: {', '.join(found_signals)}.")
            evidence.append(f"Textual severity/risk indicators (+{text_risk_score} pts)")
    else:
        evidence.append("NLP text analysis not supplied (0 pts)")

    # 3. Duplicate / Recurring Complaint Score (up to PRIORITY_WEIGHT_REPEAT = 15)
    repeat_score = 0
    if request.duplicate_analysis:
        dup = request.duplicate_analysis
        if dup.classification == "duplicate":
            repeat_score = settings.PRIORITY_WEIGHT_REPEAT
            reasons.append(f"A similar report may describe the same incident (reference {dup.matched_reference_id}); duplicate classification is not recurrence.")
            evidence.append(f"Duplicate reports detected in vicinity (+{repeat_score} pts)")
        elif dup.classification == "possible_duplicate":
            repeat_score = int(settings.PRIORITY_WEIGHT_REPEAT * 0.66)
            reasons.append(f"A nearby similar report may describe the same incident (reference {dup.matched_reference_id}); recurrence is evaluated separately.")
            evidence.append(f"Possible duplicate report nearby (+{repeat_score} pts)")
        else:
            evidence.append("Complaint verified as unique; no recurring report penalty (+0 pts)")
    else:
        evidence.append("Duplicate analysis not supplied (0 pts)")

    recurrence_score = 0
    if recurrence_analysis:
        recurrence = recurrence_analysis
        if recurrence.recurrence_detected:
            recurrence_score = min(
                settings.PRIORITY_WEIGHT_RECURRENCE,
                recurrence.recurrence_count * 2,
            )
            count_label = "at least " if not recurrence.history_scan_complete else ""
            reasons.append(
                f"Persisted history records {count_label}{recurrence.recurrence_count} prior same-category case(s) at this location outside the duplicate window."
            )
            evidence.append(f"Separate issue recurrence signal (+{recurrence_score} pts, bounded)")
        else:
            evidence.append("No qualifying persisted recurrence evidence (0 pts)")
    else:
        evidence.append("Recurrence analysis not supplied (0 pts)")

    # 4. Location Context Score (up to PRIORITY_WEIGHT_LOCATION = 10)
    location_score = 0
    if request.location_context:
        loc = request.location_context
        loc_text = f"{loc.road or ''} {loc.area or ''}".lower()

        is_major_corridor = any(kw in loc_text for kw in MAJOR_CORRIDOR_KEYWORDS)
        if is_major_corridor:
            location_score = settings.PRIORITY_WEIGHT_LOCATION
            reasons.append(f"Located along a major traffic route or sensitive public zone ('{loc.road or loc.area}').")
            evidence.append(f"Major traffic corridor / public access zone (+{location_score} pts)")
        elif loc.road or loc.area:
            location_score = int(settings.PRIORITY_WEIGHT_LOCATION * 0.5)
            evidence.append(f"Standard localized street road context (+{location_score} pts)")
        else:
            evidence.append("Location context partial or missing road details (0 pts)")
    else:
        evidence.append("Location context not supplied (0 pts)")

    # 5. Computer Vision Confidence Adjustment (up to PRIORITY_WEIGHT_CONFIDENCE = 5)
    # Treated strictly as evidence strength, NOT actual physical danger magnitude
    cv_score = 0
    if request.cv_confidence is not None:
        conf = request.cv_confidence
        if conf >= 0.85:
            cv_score = settings.PRIORITY_WEIGHT_CONFIDENCE
            reasons.append(f"Computer vision model confirmed issue with high detection confidence ({int(conf * 100)}%).")
            evidence.append(f"High computer vision detection confidence evidence (+{cv_score} pts)")
        elif conf >= 0.60:
            cv_score = int(settings.PRIORITY_WEIGHT_CONFIDENCE * 0.6)
            reasons.append(f"Computer vision model confirmed issue with moderate confidence ({int(conf * 100)}%).")
            evidence.append(f"Moderate computer vision detection confidence evidence (+{cv_score} pts)")
        else:
            cv_score = 1
            evidence.append(f"Low computer vision detection confidence evidence (+{cv_score} pts)")
    else:
        evidence.append("Computer vision confidence not supplied (0 pts)")

    # 6. Authority Context (Administrative routing evidence only)
    if request.authority_context:
        auth = request.authority_context
        if auth.authority_status == "verified":
            reasons.append("Responsible authority is officially verified, enabling direct municipal dispatch.")
            evidence.append("Official road maintenance authority verified for direct actionability.")
        elif auth.authority_status == "partially_verified":
            evidence.append("Road authority partially verified.")
        else:
            evidence.append("Road authority not verified; requires jurisdiction resolution before dispatch.")
    else:
        evidence.append("Authority context not supplied (0 pts)")

    # Compute Total Normalized Score
    raw_score = base_score + text_risk_score + repeat_score + recurrence_score + location_score + cv_score
    priority_score = max(0, min(100, int(round(raw_score))))

    # Determine Priority Level and Risk Level
    if priority_score >= settings.PRIORITY_P1_THRESHOLD:
        priority_level: PriorityLevel = "P1"
        risk_level: RiskLevel = "Critical"
    elif priority_score >= settings.PRIORITY_P2_THRESHOLD:
        priority_level = "P2"
        risk_level = "High"
    elif priority_score >= settings.PRIORITY_P3_THRESHOLD:
        priority_level = "P3"
        risk_level = "Medium"
    else:
        priority_level = "P4"
        risk_level = "Low"

    limitations = [
        "Priority scoring is an explainable engineering decision-support heuristic, not a medical or physical emergency predictor.",
        "Computer vision confidence reflects detection quality, not physical hazard magnitude.",
        "Authority verification indicates administrative clarity, not civic urgency.",
    ]

    return PriorityScoreResponse(
        priority_score=priority_score,
        priority_level=priority_level,
        risk_level=risk_level,
        recurrence_score=recurrence_score,
        reasons=reasons,
        evidence=evidence,
        limitations=limitations,
    )
