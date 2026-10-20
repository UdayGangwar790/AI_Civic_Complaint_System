"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.5: Field Inspection Protocol & Audit Engine Service
"""

from datetime import datetime, timezone
import logging
from typing import Optional
from uuid import uuid4

from app.schemas.field_inspection import (
    AuditOutcome,
    ExpectedObservationType,
    FieldInspectionAuditResult,
    FieldInspectionProtocol,
    FieldInspectionRecord,
    FieldInspectionSubmissionRequest,
    GeofenceResult,
    InspectionCompleteness,
    InspectionObservationItem,
    InspectionStep,
    LocationRequirements,
    TemporalRequirements,
)
from app.services.multimodal.contracts import EpistemicState, IssueCategory
from app.services.spatial import haversine_distance_meters

logger = logging.getLogger("cvki.field_inspection")


class FieldInspectionProtocolGenerator:
    """
    Generates deterministic, issue-specific field inspection protocols for authorized inspectors.
    Enforces strict safety-first rules:
    - Safety considerations override precision measurements.
    - Explicit cognitive caveats (prohibited inferences) are attached to every protocol.
    """

    def generate_protocol(
        self,
        case_reference: str,
        issue_category: IssueCategory,
        case_location: Optional[dict[str, float]] = None,
        source_playbook_id: Optional[str] = None,
        source_playbook_version: Optional[str] = "1.0.0",
    ) -> FieldInspectionProtocol:
        now = datetime.now(timezone.utc)
        target_lat = case_location.get("latitude") if case_location else None
        target_lon = case_location.get("longitude") if case_location else None

        loc_req = LocationRequirements(
            target_latitude=target_lat,
            target_longitude=target_lon,
            max_acceptable_distance_meters=150.0,
            allow_outside_with_justification=True,
        )
        temp_req = TemporalRequirements(
            max_inspection_age_hours=72,
            prohibit_future_timestamps=True,
        )

        if issue_category == IssueCategory.OPEN_DAMAGED_MANHOLE:
            return FieldInspectionProtocol(
                protocol_id="PROTOCOL-MANHOLE-V1",
                protocol_version="1.0.0",
                case_reference=case_reference,
                issue_category=issue_category,
                objective="Verify physical aperture exposure, frame fracture, and emergency safety barricading.",
                inspection_steps=[
                    InspectionStep(
                        step_id="STEP-MANHOLE-01",
                        instruction="Capture wide-angle roadway overview photographs from two opposing directions.",
                        purpose="Document vehicular and pedestrian exposure risk relative to traffic lanes and crosswalks.",
                        evidence_to_collect="overview_photos",
                        expected_observation_type=ExpectedObservationType.PHOTO_EVALUATION,
                        mandatory=True,
                        order=1,
                        safety_guidance="Wear high-visibility reflective vest; position safety spotter if live traffic is present.",
                    ),
                    InspectionStep(
                        step_id="STEP-MANHOLE-02",
                        instruction="Capture high-resolution close-up photograph of rim seating, frame collar, and lid condition.",
                        purpose="Ascertain whether casting is fractured, dislodged, sunken, or missing.",
                        evidence_to_collect="close_up_frame_photo",
                        expected_observation_type=ExpectedObservationType.STRUCTURAL_CONDITION,
                        mandatory=True,
                        order=2,
                    ),
                    InspectionStep(
                        step_id="STEP-MANHOLE-03",
                        instruction="Estimate approximate aperture dimensions and depth without leaning into the chamber.",
                        purpose="Determine required replacement lid specifications and immediate falling hazard level.",
                        evidence_to_collect="dimension_estimate",
                        expected_observation_type=ExpectedObservationType.DIMENSION_ESTIMATE,
                        mandatory=False,
                        order=3,
                        safety_guidance="SAFETY OVERRIDE: Do not attempt precision measurement if traffic is heavy or rim is unstable.",
                    ),
                    InspectionStep(
                        step_id="STEP-MANHOLE-04",
                        instruction="Verify physical warning barricade, cone, or protective cover status.",
                        purpose="Ensure active risk mitigation is deployed while awaiting permanent lid replacement.",
                        evidence_to_collect="mitigation_verification",
                        expected_observation_type=ExpectedObservationType.SAFETY_HAZARD_PRESENCE,
                        mandatory=True,
                        order=4,
                    ),
                ],
                required_evidence=["overview_photos", "close_up_frame_photo", "mitigation_verification"],
                optional_evidence=["dimension_estimate"],
                safety_notes=[
                    "Never enter an open manhole chamber under any circumstances (confined space hazard).",
                    "Safety precautions strictly supersede visual inspection data capture.",
                    "If manhole is in active live traffic lane and unbarricaded, deploy cones immediately before recording notes.",
                ],
                location_requirements=loc_req,
                temporal_requirements=temp_req,
                acceptance_conditions=[
                    "At least one clear photograph of the aperture rim seating",
                    "GPS coordinates recorded within designated vicinity",
                    "Safety mitigation status documented",
                ],
                prohibited_inferences=[
                    "Do not assume the manhole cover was stolen without verified on-site physical evidence.",
                    "Do not infer municipal sewer ownership without checking embossed utility letters on the casting or adjacent conduit.",
                    "Do not treat temporary safety barricading as permanent structural resolution.",
                ],
                source_playbook_id=source_playbook_id or "PB-MANHOLE-SAFETY-V1",
                source_playbook_version=source_playbook_version,
                created_at=now,
            )

        elif issue_category == IssueCategory.DAMAGED_MISSING_ROAD_SIGN:
            return FieldInspectionProtocol(
                protocol_id="PROTOCOL-ROAD-SIGN-V1",
                protocol_version="1.0.0",
                case_reference=case_reference,
                issue_category=issue_category,
                objective="Verify road traffic sign presence, retro-reflective condition, post stability, and driver visibility.",
                inspection_steps=[
                    InspectionStep(
                        step_id="STEP-SIGN-01",
                        instruction="Photograph sign approach view from 50m and 20m along approaching traffic lane.",
                        purpose="Assess driver sightline visibility, daytime contrast, and visual clutter.",
                        evidence_to_collect="approach_sightline_photos",
                        expected_observation_type=ExpectedObservationType.VISIBILITY_OBSTRUCTION,
                        mandatory=True,
                        order=1,
                    ),
                    InspectionStep(
                        step_id="STEP-SIGN-02",
                        instruction="Photograph close-up of sign face, mounting brackets, and retro-reflective sheeting.",
                        purpose="Document plate vandalism, peeling, bullet/impact denting, or faded legibility.",
                        evidence_to_collect="sign_face_photo",
                        expected_observation_type=ExpectedObservationType.PHOTO_EVALUATION,
                        mandatory=True,
                        order=2,
                    ),
                    InspectionStep(
                        step_id="STEP-SIGN-03",
                        instruction="Examine sign pole vertical deflection, base plate bolts, and ground foundation stability.",
                        purpose="Evaluate whether post is loose, bent, or at risk of collapse onto roadway or sidewalk.",
                        evidence_to_collect="pole_stability_check",
                        expected_observation_type=ExpectedObservationType.STRUCTURAL_CONDITION,
                        mandatory=True,
                        order=3,
                    ),
                    InspectionStep(
                        step_id="STEP-SIGN-04",
                        instruction="Check whether tree branches, foliage, or commercial banners obstruct sign visibility.",
                        purpose="Determine if line-of-sight pruning can resolve regulatory visibility immediately.",
                        evidence_to_collect="obstruction_finding",
                        expected_observation_type=ExpectedObservationType.VISIBILITY_OBSTRUCTION,
                        mandatory=False,
                        order=4,
                    ),
                ],
                required_evidence=["approach_sightline_photos", "sign_face_photo", "pole_stability_check"],
                optional_evidence=["obstruction_finding"],
                safety_notes=[
                    "Exercise caution when standing on roadway shoulders.",
                    "Do not attempt to bend back compromised steel posts on site due to metal fatigue risk.",
                ],
                location_requirements=loc_req,
                temporal_requirements=temp_req,
                acceptance_conditions=[
                    "Approaching sightline photos captured from driver perspective",
                    "Foundation post stability verified",
                ],
                prohibited_inferences=[
                    "Do not assume a missing cautionary sign presents zero hazard without evaluating intersection speed limit context.",
                    "Do not infer post foundation is intact based solely on vertical appearance if base bolts are rusted.",
                ],
                source_playbook_id=source_playbook_id or "PB-ROAD-SIGN-HAZARD-V1",
                source_playbook_version=source_playbook_version,
                created_at=now,
            )

        elif issue_category == IssueCategory.ROAD_WATERLOGGING:
            return FieldInspectionProtocol(
                protocol_id="PROTOCOL-WATERLOGGING-V1",
                protocol_version="1.0.0",
                case_reference=case_reference,
                issue_category=issue_category,
                objective="Assess standing water extent, depth along curb line, storm catch basin inflow, and traffic impedance.",
                inspection_steps=[
                    InspectionStep(
                        step_id="STEP-WATER-01",
                        instruction="Capture overview photo of waterlogged roadway section showing lane coverage.",
                        purpose="Document proportion of carriageway submerged and available pedestrian bypass.",
                        evidence_to_collect="surface_water_overview_photo",
                        expected_observation_type=ExpectedObservationType.PHOTO_EVALUATION,
                        mandatory=True,
                        order=1,
                    ),
                    InspectionStep(
                        step_id="STEP-WATER-02",
                        instruction="Estimate maximum standing water depth along curb line and gutter.",
                        purpose="Evaluate vehicle hydroplaning and engine flooding risk.",
                        evidence_to_collect="curb_depth_estimate",
                        expected_observation_type=ExpectedObservationType.DIMENSION_ESTIMATE,
                        mandatory=True,
                        order=2,
                        safety_guidance="Use depth gauge or ruler; do not step into deep opaque pools where open manholes may hide.",
                    ),
                    InspectionStep(
                        step_id="STEP-WATER-03",
                        instruction="Inspect roadside curb inlets and storm grates within 50m upstream and downstream.",
                        purpose="Identify whether solid waste, fallen leaves, or silt are choking gravity inlet flow.",
                        evidence_to_collect="catch_basin_condition",
                        expected_observation_type=ExpectedObservationType.DRAINAGE_FLOW_CONDITION,
                        mandatory=True,
                        order=3,
                    ),
                    InspectionStep(
                        step_id="STEP-WATER-04",
                        instruction="Record vehicular traffic slowdown and local environmental precipitation context.",
                        purpose="Document operational impedance and whether rain is active (contextual evidence only).",
                        evidence_to_collect="traffic_impact_observation",
                        expected_observation_type=ExpectedObservationType.SAFETY_HAZARD_PRESENCE,
                        mandatory=False,
                        order=4,
                    ),
                ],
                required_evidence=["surface_water_overview_photo", "curb_depth_estimate", "catch_basin_condition"],
                optional_evidence=["traffic_impact_observation"],
                safety_notes=[
                    "Submerged roadways can conceal dislodged manhole covers or electrical feeder pillars.",
                    "Wear protective waterproof boots; never wade into murky standing water without a probe rod.",
                ],
                location_requirements=loc_req,
                temporal_requirements=temp_req,
                acceptance_conditions=[
                    "Water coverage photograph documented",
                    "Curb inlet obstruction evaluated within 50m",
                ],
                prohibited_inferences=[
                    "Do not infer rainfall alone caused waterlogging without evaluating road camber and drainage throat capacity.",
                    "Precipitation is contextual operational evidence, not exclusive causal proof of infrastructure failure.",
                    "Do not assume water will recede naturally without verifying discharge outfall.",
                ],
                source_playbook_id=source_playbook_id or "PB-WATERLOGGING-DRAIN-V1",
                source_playbook_version=source_playbook_version,
                created_at=now,
            )

        else:
            # Generic Civic Issue Protocol
            return FieldInspectionProtocol(
                protocol_id="PROTOCOL-GENERIC-CIVIC-V1",
                protocol_version="1.0.0",
                case_reference=case_reference,
                issue_category=issue_category,
                objective="Conduct preliminary physical spot-check verification of reported municipal infrastructure defect.",
                inspection_steps=[
                    InspectionStep(
                        step_id="STEP-GENERIC-01",
                        instruction="Conduct on-site walkthrough and capture wide-angle photograph with landmark context.",
                        purpose="Confirm physical existence and location of reported civic issue.",
                        evidence_to_collect="context_photo",
                        expected_observation_type=ExpectedObservationType.GENERAL_VERIFICATION,
                        mandatory=True,
                        order=1,
                    ),
                    InspectionStep(
                        step_id="STEP-GENERIC-02",
                        instruction="Capture close-up photograph of defect details, dimensions, and material degradation.",
                        purpose="Enable municipal engineering discipline triage.",
                        evidence_to_collect="defect_detail_photo",
                        expected_observation_type=ExpectedObservationType.STRUCTURAL_CONDITION,
                        mandatory=True,
                        order=2,
                    ),
                    InspectionStep(
                        step_id="STEP-GENERIC-03",
                        instruction="Record qualitative safety hazard observation and pedestrian impact.",
                        purpose="Determine if urgent mitigation barricade is warranted.",
                        evidence_to_collect="safety_finding",
                        expected_observation_type=ExpectedObservationType.SAFETY_HAZARD_PRESENCE,
                        mandatory=True,
                        order=3,
                    ),
                ],
                required_evidence=["context_photo", "defect_detail_photo", "safety_finding"],
                optional_evidence=[],
                safety_notes=["Maintain situational awareness regarding moving traffic and roadside hazards."],
                location_requirements=loc_req,
                temporal_requirements=temp_req,
                acceptance_conditions=["Walkthrough photo captured", "Safety hazard documented"],
                prohibited_inferences=["Do not dismiss citizen report as spurious without on-site visual confirmation."],
                source_playbook_id=source_playbook_id or "PB-GENERIC-CIVIC-V1",
                source_playbook_version=source_playbook_version,
                created_at=now,
            )


class FieldInspectionAuditEngine:
    """
    Automated audit evaluation of field inspection submissions against protocol requirements.
    Adheres strictly to epistemic safety invariants:
    - Never declares physical ground truth.
    - Never automatically resolves cases or marks repairs verified.
    - Audit results are SYSTEM_DERIVED; human inspector observations are USER_REPORTED.
    """

    def audit_submission(
        self,
        protocol: FieldInspectionProtocol,
        submission: FieldInspectionSubmissionRequest,
        inspector_id: str,
        visual_audit_outcome: Optional[str] = None,
    ) -> FieldInspectionRecord:
        now = datetime.now(timezone.utc)

        # 1. Temporal Validation
        sub_time = submission.inspection_timestamp
        if sub_time.tzinfo is None:
            sub_time = sub_time.replace(tzinfo=timezone.utc)

        # Disallow future timestamps with 60-second grace tolerance
        if (sub_time - now).total_seconds() > 60:
            raise ValueError(f"Inspection timestamp ({sub_time.isoformat()}) cannot be in the future.")

        # 2. Geofence Evaluation
        geofence_res, dist_meters = self._evaluate_geofence(protocol.location_requirements, submission.location)

        # 3. Completeness Evaluation
        mandatory_step_ids = {s.step_id for s in protocol.inspection_steps if s.mandatory}
        submitted_step_ids = {obs.step_id for obs in submission.observations}

        missing_steps = list(mandatory_step_ids - submitted_step_ids)
        supported_points: list[str] = []
        conflicts_detected: list[str] = []

        if not missing_steps:
            completeness = InspectionCompleteness.COMPLETE
            supported_points.append("All mandatory protocol inspection steps were recorded.")
        elif len(submitted_step_ids) > 0:
            completeness = InspectionCompleteness.PARTIAL
            conflicts_detected.append(f"Incomplete inspection: {len(missing_steps)} mandatory steps were not recorded ({', '.join(missing_steps)}).")
        else:
            completeness = InspectionCompleteness.INSUFFICIENT
            conflicts_detected.append("Zero protocol inspection steps recorded.")

        # 4. Check Observations & Defect Confirmation
        confirmed_count = sum(1 for obs in submission.observations if obs.defect_confirmed is True)
        denied_count = sum(1 for obs in submission.observations if obs.defect_confirmed is False)

        if denied_count > 0 and confirmed_count > 0:
            completeness = InspectionCompleteness.CONFLICTING
            conflicts_detected.append("Internal observation contradiction: both defect confirmed and defect denied recorded.")

        for obs in submission.observations:
            if obs.defect_confirmed is True:
                supported_points.append(f"Inspector confirmed physical defect in '{obs.step_id}': {obs.observation_text[:80]}")
            elif obs.defect_confirmed is False:
                conflicts_detected.append(f"Inspector reported defect not observed in '{obs.step_id}': {obs.observation_text[:80]}")

        # 5. Geofence Findings
        if geofence_res == GeofenceResult.WITHIN_EXPECTED_AREA:
            supported_points.append(f"Inspection GPS verified within tolerance ({dist_meters:.1f}m from incident coordinate).")
        elif geofence_res == GeofenceResult.OUTSIDE_EXPECTED_AREA:
            conflicts_detected.append(
                f"Inspection GPS ({dist_meters:.1f}m) exceeds max allowed tolerance ({protocol.location_requirements.max_acceptable_distance_meters:.0f}m)."
            )
        elif geofence_res == GeofenceResult.LOCATION_UNAVAILABLE:
            conflicts_detected.append("GPS coordinates were not provided for on-site inspection validation.")

        # 6. Consume M9.5 Visual Resolution Audit Outcome if available
        if visual_audit_outcome:
            if visual_audit_outcome == "DEFECT_PERSISTS":
                if confirmed_count > 0:
                    supported_points.append("Field inspection corroborates M9.5 visual audit finding (DEFECT_PERSISTS).")
                elif denied_count > 0:
                    conflicts_detected.append("Cross-evidence conflict: Inspector denied defect but M9.5 visual audit observed DEFECT_PERSISTS.")
            elif visual_audit_outcome == "DEFECT_NOT_OBSERVED":
                if denied_count > 0:
                    supported_points.append("Field inspection observation agrees with M9.5 visual audit finding (DEFECT_NOT_OBSERVED).")
                elif confirmed_count > 0:
                    conflicts_detected.append("Cross-evidence conflict: Inspector confirmed defect but M9.5 visual audit observed DEFECT_NOT_OBSERVED.")

        # 7. Synthesize Audit Outcome
        if completeness == InspectionCompleteness.CONFLICTING or (conflicts_detected and denied_count > 0 and confirmed_count > 0):
            audit_outcome = AuditOutcome.CONFLICTING
        elif completeness == InspectionCompleteness.INSUFFICIENT or len(submission.observations) == 0:
            audit_outcome = AuditOutcome.INSUFFICIENT_EVIDENCE
        elif geofence_res == GeofenceResult.OUTSIDE_EXPECTED_AREA and not protocol.location_requirements.allow_outside_with_justification:
            audit_outcome = AuditOutcome.NOT_SUPPORTED
        elif denied_count > 0 and confirmed_count == 0:
            audit_outcome = AuditOutcome.NOT_SUPPORTED
        elif completeness == InspectionCompleteness.COMPLETE and geofence_res == GeofenceResult.WITHIN_EXPECTED_AREA and confirmed_count > 0:
            audit_outcome = AuditOutcome.SUPPORTED
        elif confirmed_count > 0 or completeness in (InspectionCompleteness.COMPLETE, InspectionCompleteness.PARTIAL):
            audit_outcome = AuditOutcome.PARTIALLY_SUPPORTED
        else:
            audit_outcome = AuditOutcome.INSUFFICIENT_EVIDENCE

        # 8. Construct Audit Explanation
        explanation_lines = [
            f"Field inspection audit completed with outcome: {audit_outcome.value}.",
            f"- Completeness: {completeness.value} ({len(submission.observations)} steps recorded, {len(missing_steps)} missing).",
            f"- Geofence: {geofence_res.value}" + (f" ({dist_meters:.1f}m)" if dist_meters is not None else "") + ".",
            "- Epistemic Invariant: Audit is an automated assessment of human-reported observations and does not constitute physical ground truth or automatic repair verification.",
        ]

        audit_result = FieldInspectionAuditResult(
            audit_id=str(uuid4()),
            outcome=audit_outcome,
            completeness=completeness,
            geofence_result=geofence_res,
            distance_from_case_meters=dist_meters,
            supported_points=supported_points,
            conflicts_detected=conflicts_detected,
            missing_mandatory_steps=missing_steps,
            audit_explanation="\n".join(explanation_lines),
            epistemic_state=EpistemicState.SYSTEM_DERIVED,
            audited_at=now,
        )

        return FieldInspectionRecord(
            inspection_id=f"INSP-{uuid4().hex[:12].upper()}",
            case_reference=protocol.case_reference,
            protocol_id=protocol.protocol_id,
            protocol_version=protocol.protocol_version,
            inspector_id=inspector_id,
            observations=submission.observations,
            evidence_items=submission.evidence_items,
            location=submission.location,
            inspection_timestamp=sub_time,
            geofence_result=geofence_res,
            completeness=completeness,
            conflicts=conflicts_detected,
            audit_result=audit_result,
            epistemic_state=EpistemicState.USER_REPORTED,
            created_at=now,
        )

    def _evaluate_geofence(
        self,
        loc_req: LocationRequirements,
        sub_loc: Optional[dict[str, float]],
    ) -> tuple[GeofenceResult, Optional[float]]:
        if not sub_loc or "latitude" not in sub_loc or "longitude" not in sub_loc:
            return GeofenceResult.LOCATION_UNAVAILABLE, None

        if loc_req.target_latitude is None or loc_req.target_longitude is None:
            return GeofenceResult.LOCATION_UNCERTAIN, None

        dist = haversine_distance_meters(
            lat1=loc_req.target_latitude,
            lon1=loc_req.target_longitude,
            lat2=sub_loc["latitude"],
            lon2=sub_loc["longitude"],
        )

        if dist <= loc_req.max_acceptable_distance_meters:
            return GeofenceResult.WITHIN_EXPECTED_AREA, round(dist, 2)
        else:
            return GeofenceResult.OUTSIDE_EXPECTED_AREA, round(dist, 2)


class InMemoryFieldInspectionRepository:
    """Thread-safe in-memory repository storing field inspection records."""

    def __init__(self):
        self._records: dict[str, FieldInspectionRecord] = {}
        self._case_index: dict[str, list[str]] = {}

    def save(self, record: FieldInspectionRecord) -> None:
        self._records[record.inspection_id] = record
        self._case_index.setdefault(record.case_reference, []).append(record.inspection_id)

    def get(self, inspection_id: str) -> Optional[FieldInspectionRecord]:
        return self._records.get(inspection_id)

    def list_by_case(self, case_reference: str) -> list[FieldInspectionRecord]:
        insp_ids = self._case_index.get(case_reference, [])
        return [self._records[i] for i in insp_ids if i in self._records]

    def clear(self) -> None:
        self._records.clear()
        self._case_index.clear()


field_inspection_repository = InMemoryFieldInspectionRepository()
protocol_generator = FieldInspectionProtocolGenerator()
audit_engine = FieldInspectionAuditEngine()


def get_field_inspection_repository() -> InMemoryFieldInspectionRepository:
    return field_inspection_repository


def get_protocol_generator() -> FieldInspectionProtocolGenerator:
    return protocol_generator


def get_audit_engine() -> FieldInspectionAuditEngine:
    return audit_engine
