from datetime import datetime, timezone
import inspect
import logging
from typing import Any, Optional

from app.schemas.authority import AuthorityParty, AuthorityResult, OfficialSourceRecord
from app.schemas.complaint_case import ComplaintCase
from app.schemas.government_submission import (
    GovernmentSubmissionPackage,
    GovernmentSubmissionRecord,
    GovernmentSubmissionStatus,
    PrepareSubmissionResponse,
    ReadinessStatus,
    SubmissionReadinessResponse,
)
from app.services.authority import has_verified_builder_evidence

logger = logging.getLogger("cvki.government_submission")


class SubmissionBlockedError(RuntimeError):
    """The complaint cannot be prepared for dispatch due to unverified authority or critical policy blocks."""


class SubmissionNotReadyError(ValueError):
    """The complaint is missing required fields for submission preparation."""


SUBMISSION_LIMITATIONS = [
    "CVKI prepares structured dispatch packages but does not automatically submit complaints to external government portals.",
    "External government submission status remains 'NOT_SUBMITTED' until manual citizen submission or verified future dispatch integration.",
    "CVKI does not generate government acknowledgment, token, or grievance registration numbers.",
    "Government dispatch packages must only target verified public authorities supported by official public records.",
]


def check_submission_readiness(case: ComplaintCase) -> SubmissionReadinessResponse:
    """
    Evaluates whether a CVKI complaint case meets all structural and official authority criteria
    for government dispatch packaging.
    """
    missing_fields: list[str] = []
    reasons: list[str] = []

    # 1. Evaluate complaint text and issue definition
    if not case.complaint or not case.complaint.title or not case.complaint.title.strip():
        missing_fields.append("complaint.title")
    if not case.complaint or not case.complaint.description or not case.complaint.description.strip():
        missing_fields.append("complaint.description")
    if not case.issue or not case.issue.class_name:
        missing_fields.append("issue.class_name")

    # 2. Evaluate location context
    has_road = bool(case.location and case.location.road and case.location.road.strip())
    has_coords = bool(case.location and case.location.latitude is not None and case.location.longitude is not None)
    if not has_road and not has_coords:
        missing_fields.append("location")

    # 3. Evaluate authority verification state
    auth: Optional[AuthorityResult] = case.authority
    auth_status = auth.authority_status if auth else "not_verified"
    official_sources: list[OfficialSourceRecord] = list(auth.sources) if auth and auth.sources else []

    readiness_status: ReadinessStatus
    submission_status: GovernmentSubmissionStatus

    if case.government_submission:
        current_sub_status = case.government_submission.submission_status
    else:
        current_sub_status = "NOT_PREPARED"

    if auth is None or auth_status == "not_verified":
        readiness_status = "blocked"
        submission_status = "SUBMISSION_BLOCKED"
        reasons.append("Responsible authority could not be verified from official government sources. Submission is blocked to prevent misdirected dispatch.")
        if missing_fields:
            reasons.append(f"Additional missing fields: {', '.join(missing_fields)}.")
    elif missing_fields:
        readiness_status = "not_ready"
        submission_status = "NOT_PREPARED"
        reasons.append(f"Required complaint fields missing: {', '.join(missing_fields)}.")
    elif auth_status == "partially_verified":
        readiness_status = "partially_ready"
        submission_status = "READY_FOR_REVIEW" if current_sub_status == "NOT_PREPARED" else current_sub_status
        reasons.append("Authority information is partially verified against public sources. Citizen review is required before external submission.")
    elif auth_status == "verified":
        readiness_status = "ready"
        submission_status = "READY_FOR_REVIEW" if current_sub_status == "NOT_PREPARED" else current_sub_status
        reasons.append("All complaint requirements and verified government authority records are present.")
    else:
        readiness_status = "blocked"
        submission_status = "SUBMISSION_BLOCKED"
        reasons.append(f"Unknown authority status '{auth_status}'.")

    return SubmissionReadinessResponse(
        reference_id=case.reference_id,
        readiness_status=readiness_status,
        submission_status=submission_status,
        authority_status=auth_status,
        reasons=reasons,
        missing_fields=missing_fields,
        official_sources=official_sources,
        limitations=list(SUBMISSION_LIMITATIONS),
    )


async def prepare_government_submission(
    case: ComplaintCase,
    user_id: str,
) -> tuple[ComplaintCase, PrepareSubmissionResponse]:
    """
    Safely compiles a structured government submission package without external portal transmission.
    Guarantees external submission status remains NOT_SUBMITTED.
    """
    readiness = check_submission_readiness(case)

    if readiness.readiness_status == "blocked":
        raise SubmissionBlockedError(
            f"Cannot prepare government submission for case {case.reference_id}: {'; '.join(readiness.reasons)}"
        )
    if readiness.readiness_status == "not_ready":
        raise SubmissionNotReadyError(
            f"Cannot prepare government submission for case {case.reference_id}: Missing required fields: {', '.join(readiness.missing_fields)}"
        )

    now = datetime.now(timezone.utc)

    supported_builder: Optional[AuthorityParty] = None
    if case.authority and case.authority.builder_or_contractor:
        if has_verified_builder_evidence(case.authority.evidence or []):
            supported_builder = case.authority.builder_or_contractor

    loc_dict = case.location.model_dump() if case.location else {}

    package = GovernmentSubmissionPackage(
        reference_id=case.reference_id,
        issue_category=case.issue.class_name,
        complaint_title=case.complaint.title,
        complaint_description=case.complaint.description,
        detected_location=loc_dict,
        road=case.location.road if case.location else None,
        area=case.location.area if case.location else None,
        city=case.location.city if case.location else None,
        district=case.location.district if case.location else None,
        state=case.location.state if case.location else None,
        country=getattr(case.location, "country", None) or "India",
        authority_verification_state=case.authority.authority_status,
        road_owner=case.authority.road_owner,
        maintenance_authority=case.authority.maintenance_authority,
        builder_or_contractor=supported_builder,
        official_evidence_records=list(case.authority.evidence) if case.authority else [],
        priority=case.priority_analysis.model_dump() if case.priority_analysis else None,
        nlp_analysis_summary=case.nlp_analysis.normalized_summary if case.nlp_analysis else None,
        duplicate_status=case.duplicate_analysis.classification if case.duplicate_analysis else None,
        created_at=case.created_at,
        prepared_at=now,
        submission_status="NOT_SUBMITTED",
    )

    package_status: GovernmentSubmissionStatus = (
        "READY_FOR_REVIEW" if readiness.readiness_status == "partially_ready" else "PREPARED"
    )

    record = GovernmentSubmissionRecord(
        readiness_status=readiness.readiness_status,
        submission_status=package_status,
        prepared_at=now,
        authority_status=case.authority.authority_status,
        package=package,
        official_sources=list(case.authority.sources) if case.authority else [],
        limitations=list(SUBMISSION_LIMITATIONS),
        review_required=(readiness.readiness_status == "partially_ready"),
        prepared_by_user_id=user_id,
    )

    case.government_submission = record
    case.updated_at = now

    # Persist updated case
    from app.services import complaint_case as cc_mod
    saved = cc_mod.case_repository.save(case)
    if inspect.isawaitable(saved):
        updated_case = await saved
    else:
        updated_case = saved

    # Trigger in-app notification for prepared government submission
    try:
        from app.services.notification import trigger_gov_submission_prepared_notification
        await trigger_gov_submission_prepared_notification(updated_case)
    except Exception as exc:
        logger.warning("Failed to trigger government submission prepared notification: %s", exc)

    response = PrepareSubmissionResponse(
        reference_id=case.reference_id,
        submission_status=package_status,
        readiness_status=readiness.readiness_status,
        prepared_at=now,
        authority=case.authority,
        package=package,
        limitations=list(SUBMISSION_LIMITATIONS),
    )

    return updated_case, response
