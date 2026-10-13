from datetime import datetime, timezone
import logging
import math
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings
from app.schemas.duplicate import DuplicateCheckRequest, DuplicateCheckResponse
import app.services.complaint_case as complaint_case_module

logger = logging.getLogger("cvki.duplicate")


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes great-circle distance between two GPS coordinates in meters using the Haversine formula.
    """
    earth_radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_m * c


def compute_text_similarity(text1: str, text2: str) -> float:
    """
    Computes text similarity using TF-IDF cosine similarity.
    Uses sublinear TF with word and character n-grams for robust multilingual/Hinglish matching.
    """
    t1 = text1.strip().lower()
    t2 = text2.strip().lower()

    if not t1 or not t2:
        return 0.0

    if t1 == t2:
        return 1.0

    try:
        # Word-level TF-IDF
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), lowercase=True, sublinear_tf=True)
        tfidf_matrix = vectorizer.fit_transform([t1, t2])
        word_sim = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])
    except Exception:
        word_sim = 0.0

    try:
        # Character n-gram TF-IDF for phonetic/typo cross-matching in Hinglish
        char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True)
        char_matrix = char_vectorizer.fit_transform([t1, t2])
        char_sim = float(cosine_similarity(char_matrix[0:1], char_matrix[1:2])[0][0])
    except Exception:
        char_sim = 0.0

    # Blended score: 60% word-level, 40% char-level
    combined_sim = max(word_sim, (word_sim * 0.60 + char_sim * 0.40))
    return min(1.0, max(0.0, combined_sim))


async def check_complaint_duplicate(
    request: DuplicateCheckRequest,
    raise_on_db_error: bool = True,
) -> DuplicateCheckResponse:
    """
    Evaluates whether a complaint is unique, possible_duplicate, or duplicate
    against existing CVKI cases using multi-signal spatiotemporal and semantic similarity.
    Does NOT leak private complaint contents or citizen identities.
    """
    req_time = request.created_at or datetime.now(timezone.utc)
    if req_time.tzinfo is None:
        req_time = req_time.replace(tzinfo=timezone.utc)

    repo = complaint_case_module.case_repository
    # Fetch candidate cases from the active repository
    try:
        if hasattr(repo, "list_recent_candidates"):
            candidates = await repo.list_recent_candidates(limit=100)
        elif hasattr(repo, "_cases"):
            candidates = list(repo._cases.values())
        else:
            candidates = []
    except complaint_case_module.ComplaintCaseDatabaseError:
        if raise_on_db_error:
            raise
        logger.warning("Database unavailable during duplicate check; returning safe unique result.")
        return DuplicateCheckResponse(
            classification="unique",
            similarity_score=0.0,
            matched_reference_id=None,
            distance_meters=None,
            time_difference_hours=None,
            issue_match=False,
            reason="Persistence store unavailable for duplicate comparison; complaint treated as unique.",
        )
    except Exception as exc:
        logger.warning("Error fetching candidates for duplicate check: %s", exc)
        candidates = []

    if not candidates:
        return DuplicateCheckResponse(
            classification="unique",
            similarity_score=0.0,
            matched_reference_id=None,
            distance_meters=None,
            time_difference_hours=None,
            issue_match=False,
            reason="No existing complaint cases found for comparison.",
        )

    best_match = None
    best_classification = "unique"
    highest_similarity = 0.0
    matched_distance = None
    matched_time_diff = None
    matched_issue_match = False
    match_reason = "No similar active complaint found nearby within configured thresholds."

    for candidate in candidates:
        cand_issue = candidate.issue.class_name
        issue_match = (cand_issue == request.issue_category)

        # Different civic issues at the same place are NOT duplicates
        if not issue_match:
            continue

        matched_issue_match = True

        cand_time = candidate.created_at
        if cand_time.tzinfo is None:
            cand_time = cand_time.replace(tzinfo=timezone.utc)

        time_diff_hours = abs((req_time - cand_time).total_seconds()) / 3600.0

        # Calculate semantic similarity against candidate complaint title + description
        cand_text = f"{candidate.complaint.title} {candidate.complaint.description}".strip()
        sim_score = compute_text_similarity(request.complaint_text, cand_text)

        # Calculate geographic distance if coordinates are present on both
        cand_loc = candidate.location
        has_coords = (
            request.latitude is not None
            and request.longitude is not None
            and cand_loc.latitude is not None
            and cand_loc.longitude is not None
        )

        dist_meters = None
        if has_coords:
            dist_meters = haversine_distance_meters(
                request.latitude, request.longitude,
                cand_loc.latitude, cand_loc.longitude,
            )

        # Spatiotemporal Decision Logic
        cand_classification = "unique"
        cand_reason = "Complaint appears unique."

        # Case 1: Coordinates available
        if dist_meters is not None:
            if dist_meters > 5000.0:
                # Far away (> 5km): different location, cannot be duplicate even if identical text
                cand_classification = "unique"
                cand_reason = f"Same issue category reported at a distant location ({dist_meters / 1000.0:.1f} km away)."
            elif dist_meters <= settings.DUPLICATE_DISTANCE_METERS:
                # Within duplicate radius (e.g. <= 150m)
                if (
                    sim_score >= settings.DUPLICATE_SIMILARITY_THRESHOLD
                    and time_diff_hours <= settings.DUPLICATE_TIME_WINDOW_HOURS
                ):
                    cand_classification = "duplicate"
                    cand_reason = (
                        f"Duplicate detected: high similarity ({sim_score:.2f}) and physical proximity "
                        f"({dist_meters:.0f}m) for {cand_issue} within {time_diff_hours:.1f}h."
                    )
                elif (
                    sim_score >= settings.POSSIBLE_DUPLICATE_SIMILARITY_THRESHOLD
                    or dist_meters <= 50.0
                ) and time_diff_hours <= settings.DUPLICATE_TIME_WINDOW_HOURS:
                    cand_classification = "possible_duplicate"
                    cand_reason = (
                        f"Possible duplicate: nearby report ({dist_meters:.0f}m) for {cand_issue} "
                        f"with text similarity {sim_score:.2f} within {time_diff_hours:.1f}h."
                    )
                else:
                    cand_classification = "unique"
                    cand_reason = f"Nearby report exists ({dist_meters:.0f}m), but elapsed time or distinct description indicates a distinct report."
            else:
                # Between 150m and 5km
                if sim_score >= 0.85 and dist_meters <= 500.0 and time_diff_hours <= settings.DUPLICATE_TIME_WINDOW_HOURS:
                    cand_classification = "possible_duplicate"
                    cand_reason = f"Possible duplicate: high text similarity ({sim_score:.2f}) within {dist_meters:.0f}m in the same vicinity."
                else:
                    cand_classification = "unique"
                    cand_reason = f"Distinct location ({dist_meters:.0f}m away)."

        # Case 2: Missing coordinates on either
        else:
            if (
                sim_score >= 0.90
                and time_diff_hours <= settings.DUPLICATE_TIME_WINDOW_HOURS
            ):
                cand_classification = "possible_duplicate"
                cand_reason = (
                    f"Possible duplicate based on very high text similarity ({sim_score:.2f}) "
                    f"within {time_diff_hours:.1f}h; coordinates missing for physical proximity check."
                )
            else:
                cand_classification = "unique"
                cand_reason = "No coordinates available to verify physical proximity and text similarity is below threshold."

        # Keep the strongest classification (duplicate > possible_duplicate > unique)
        rank = {"duplicate": 3, "possible_duplicate": 2, "unique": 1}
        current_rank = rank.get(cand_classification, 1)
        best_rank = rank.get(best_classification, 1)

        if (
            current_rank > best_rank
            or (current_rank == best_rank and sim_score > highest_similarity)
        ):
            best_match = candidate
            best_classification = cand_classification
            highest_similarity = sim_score
            matched_distance = dist_meters
            matched_time_diff = time_diff_hours
            match_reason = cand_reason

    matched_ref = best_match.reference_id if (best_match and best_classification != "unique") else None

    return DuplicateCheckResponse(
        classification=best_classification,
        similarity_score=round(highest_similarity, 3),
        matched_reference_id=matched_ref,
        distance_meters=round(matched_distance, 1) if matched_distance is not None else None,
        time_difference_hours=round(matched_time_diff, 1) if matched_time_diff is not None else None,
        issue_match=matched_issue_match,
        reason=match_reason,
        method="tfidf_cosine_similarity_with_spatiotemporal_heuristic",
    )
