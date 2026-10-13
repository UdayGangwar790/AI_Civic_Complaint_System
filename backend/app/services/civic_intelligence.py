from datetime import datetime, timedelta, timezone
import inspect
import logging

from app.core.config import settings
from app.models.roles import UserRole
from app.schemas.civic_intelligence import (
    CaseIntelligenceResponse,
    CivicRecommendation,
    RecurrenceAnalysis,
)
from app.schemas.complaint import ComplaintLocation
from app.schemas.complaint_case import ComplaintCase
from app.services.duplicate import haversine_distance_meters
import app.services.complaint_case as complaint_case_module

logger = logging.getLogger("cvki.civic_intelligence")

FINAL_CASE_STATUSES = {"resolved", "closed"}


def _normalized_location_part(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _same_location_for_recurrence(current_location: ComplaintLocation, previous: ComplaintCase) -> bool:
    previous_location = previous.location
    if all(value is not None for value in (
        current_location.latitude,
        current_location.longitude,
        previous_location.latitude,
        previous_location.longitude,
    )):
        return haversine_distance_meters(
            current_location.latitude,
            current_location.longitude,
            previous_location.latitude,
            previous_location.longitude,
        ) <= 250

    current_road = _normalized_location_part(current_location.road)
    current_city = _normalized_location_part(current_location.city)
    return bool(
        current_road
        and current_city
        and current_road == _normalized_location_part(previous_location.road)
        and current_city == _normalized_location_part(previous_location.city)
    )


async def _load_recent_cases() -> tuple[list[ComplaintCase], bool]:
    limit = settings.MAX_INTELLIGENCE_HISTORY_CANDIDATES
    try:
        cases = await complaint_case_module.case_repository.list_recent_candidates(limit=limit + 1)
    except complaint_case_module.ComplaintCaseDatabaseError:
        raise
    except Exception as exc:
        logger.warning("Civic intelligence history scan failed (error_type=%s).", type(exc).__name__)
        return [], False
    complete = len(cases) <= limit
    return cases[:limit], complete


def _build_recurrence_analysis(
    reference_id: str,
    issue_category: str,
    location: ComplaintLocation,
    created_at: datetime,
    candidates: list[ComplaintCase],
    *,
    history_scan_complete: bool,
    include_case_ids: bool,
) -> RecurrenceAnalysis:
    case_time = _as_utc(created_at)
    window_days = settings.RECURRENCE_WINDOW_DAYS
    earliest_time = case_time - timedelta(days=window_days)
    duplicate_separation = timedelta(hours=settings.DUPLICATE_TIME_WINDOW_HOURS)
    recurrence_distance = 250
    matches: list[ComplaintCase] = []

    for previous in candidates:
        if previous.reference_id == reference_id:
            continue
        if previous.issue.class_name != issue_category or previous.status == "draft":
            continue
        previous_time = _as_utc(previous.created_at)
        if not (earliest_time <= previous_time < case_time - duplicate_separation):
            continue
        if not _same_location_for_recurrence(location, previous):
            continue
        matches.append(previous)

    matches.sort(key=lambda item: (item.created_at, item.reference_id), reverse=True)
    count = len(matches)
    detected = count > 0
    if detected:
        qualifier = "at least " if not history_scan_complete else ""
        explanation = (
            f"Found {qualifier}{count} prior case(s) for the same issue category within "
            f"{recurrence_distance} m (or the same normalized road and city when coordinates are missing), "
            f"spanning more than {settings.DUPLICATE_TIME_WINDOW_HOURS:g} hours and within the last {window_days} days. "
            "This indicates repeated reports, not proof that reports describe the same physical defect."
        )
    elif history_scan_complete:
        explanation = (
            f"No prior same-category case met the {recurrence_distance} m location and "
            f"{settings.DUPLICATE_TIME_WINDOW_HOURS:g}-hour separation rules in the last {window_days} days; "
            "there is insufficient historical evidence to identify recurrence."
        )
    else:
        explanation = (
            f"No matching case was found in the most recent {settings.MAX_INTELLIGENCE_HISTORY_CANDIDATES} "
            "records scanned; the history scan was capped, so absence of recurrence cannot be established."
        )

    return RecurrenceAnalysis(
        recurrence_detected=detected,
        recurrence_count=count,
        related_historical_case_ids=(
            [item.reference_id for item in matches]
            if include_case_ids
            else []
        ),
        recurrence_window_days=window_days,
        history_scan_complete=history_scan_complete,
        recurrence_explanation=explanation,
    )


async def analyze_recurrence_for_new_case(
    issue_category: str,
    location: ComplaintLocation,
    created_at: datetime,
) -> RecurrenceAnalysis:
    candidates, scan_complete = await _load_recent_cases()
    return _build_recurrence_analysis(
        reference_id="",
        issue_category=issue_category,
        location=location,
        created_at=created_at,
        candidates=candidates,
        history_scan_complete=scan_complete,
        include_case_ids=False,
    )


def _resolution_evidence_state(case: ComplaintCase) -> tuple[str, str]:
    if case.status not in FINAL_CASE_STATUSES:
        return (
            "status_only",
            f"Case is currently marked {case.status.replace('_', ' ')}; no resolution claim is active.",
        )

    evidence_since_resolution = [
        item
        for item in case.resolution_evidence
        if case.resolution_evidence_recorded_at is None
        or _as_utc(item.recorded_at) >= _as_utc(case.resolution_evidence_recorded_at)
    ]
    if evidence_since_resolution:
        return (
            "evidence_supported",
            "Case is marked resolved and contains an attributed staff resolution note. "
            "CVKI has not independently verified that physical repair occurred.",
        )
    return (
        "evidence_missing",
        "Case is marked resolved, but no current resolution evidence is recorded.",
    )


def _same_recent_road_city(case: ComplaintCase, other: ComplaintCase) -> bool:
    road = _normalized_location_part(case.location.road)
    city = _normalized_location_part(case.location.city)
    return bool(
        road
        and city
        and road == _normalized_location_part(other.location.road)
        and city == _normalized_location_part(other.location.city)
    )


async def get_case_intelligence(
    reference_id: str,
    actor_user_id: str,
    actor_role: str,
) -> CaseIntelligenceResponse:
    repository = complaint_case_module.case_repository
    case = repository.get(reference_id)
    if inspect.isawaitable(case):
        case = await case

    if actor_role == UserRole.AUTHORITY.value:
        assigned_user_id = case.assignment.assigned_to_user_id if case.assignment else None
        if assigned_user_id != actor_user_id:
            raise PermissionError("Authorities can only view intelligence for cases assigned to them.")
        include_case_ids = False
    elif actor_role == UserRole.ADMIN.value:
        include_case_ids = True
    else:
        raise PermissionError("Case intelligence is not available for this role.")

    candidates, scan_complete = await _load_recent_cases()
    recurrence = _build_recurrence_analysis(
        reference_id=case.reference_id,
        issue_category=case.issue.class_name,
        location=case.location,
        created_at=case.created_at,
        candidates=candidates,
        history_scan_complete=scan_complete,
        include_case_ids=include_case_ids,
    )

    hotspot_window_days = settings.HOTSPOT_WINDOW_DAYS
    cutoff = _as_utc(case.created_at) - timedelta(days=hotspot_window_days)
    recent_location_cases = [
        item
        for item in candidates
        if cutoff <= _as_utc(item.created_at) <= _as_utc(case.created_at)
        and _same_recent_road_city(case, item)
    ]
    unresolved_count = sum(item.status not in FINAL_CASE_STATUSES for item in recent_location_cases)
    issue_counts: dict[str, int] = {}
    for item in recent_location_cases:
        issue_counts[item.issue.class_name] = issue_counts.get(item.issue.class_name, 0) + 1
    dominant_issue = sorted(issue_counts.items(), key=lambda entry: (-entry[1], entry[0]))[0][0] if issue_counts else None
    hotspot_detected = len(recent_location_cases) >= settings.HOTSPOT_MIN_CASES

    if hotspot_detected:
        hotspot_explanation = (
            f"{len(recent_location_cases)} persisted reports share this road and city in the previous "
            f"{hotspot_window_days} days; {unresolved_count} are not resolved or closed. "
            "This is a reporting concentration, not proof of a common cause."
        )
    elif not case.location.road or not case.location.city:
        hotspot_explanation = "Road and city are both needed to assess a local reporting concentration."
    else:
        hotspot_explanation = (
            f"Fewer than {settings.HOTSPOT_MIN_CASES} persisted reports share this road and city "
            f"in the previous {hotspot_window_days} days; no hotspot is indicated."
        )

    evidence_state, evidence_explanation = _resolution_evidence_state(case)
    recommendations: list[CivicRecommendation] = []
    if recurrence.recurrence_detected:
        recommendations.append(CivicRecommendation(
            kind="recurrence",
            message="Similar issue categories were reported at this location previously. Consider inspecting the underlying road condition.",
            basis=recurrence.recurrence_explanation,
        ))
    if hotspot_detected:
        recommendations.append(CivicRecommendation(
            kind="hotspot",
            message="This road and city have a concentration of recent reports. Consider prioritizing field inspection.",
            basis=hotspot_explanation,
        ))

    age_days = max(0, (_as_utc(datetime.now(timezone.utc)) - _as_utc(case.created_at)).days)
    if case.status not in FINAL_CASE_STATUSES and age_days >= settings.UNRESOLVED_RECOMMENDATION_DAYS:
        recommendations.append(CivicRecommendation(
            kind="unresolved_duration",
            message="This case has remained open for an extended period. Consider reviewing its assignment and status.",
            basis=f"Stored case status is {case.status}; age is {age_days} days.",
        ))
    if evidence_state == "evidence_missing":
        recommendations.append(CivicRecommendation(
            kind="resolution_evidence_missing",
            message="The case is marked resolved but has no current resolution note. Consider recording the available inspection evidence.",
            basis=evidence_explanation,
        ))

    limitations = [
        "Recommendations are deterministic decision support based on stored CVKI records; they do not direct or compel an authority action.",
        "A staff-authored resolution note is not independent verification that physical repair occurred.",
    ]
    if not scan_complete:
        limitations.append(
            f"Historical analysis was capped at {settings.MAX_INTELLIGENCE_HISTORY_CANDIDATES} recent cases; counts may be lower bounds."
        )

    return CaseIntelligenceResponse(
        reference_id=case.reference_id,
        recurrence=recurrence,
        recent_location_case_count=len(recent_location_cases),
        recent_location_unresolved_count=unresolved_count,
        hotspot_detected=hotspot_detected,
        dominant_issue_category=dominant_issue,
        hotspot_window_days=hotspot_window_days,
        hotspot_explanation=hotspot_explanation,
        resolution_evidence_state=evidence_state,
        resolution_evidence_explanation=evidence_explanation,
        priority_level=case.priority_analysis.priority_level if case.priority_analysis else None,
        priority_score=case.priority_analysis.priority_score if case.priority_analysis else None,
        priority_reasons=list(case.priority_analysis.reasons) if case.priority_analysis else [],
        recommendations=recommendations,
        limitations=limitations,
    )