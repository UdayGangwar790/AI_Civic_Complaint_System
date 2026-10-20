"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.3: Civic Action Playbook Knowledge Base & Registry Service
"""

from datetime import datetime, timezone
import logging
from typing import Optional

from app.schemas.action_playbook import (
    ActionCategory,
    ActionPlaybook,
    ActionUrgency,
    PlaybookActionItem,
    PlaybookEvidenceRequirements,
    PlaybookMatchResult,
    PlaybookTriggerConditions,
)
from app.services.multimodal.contracts import IssueCategory

logger = logging.getLogger("cvki.action_playbooks")


class ActionPlaybookRegistry:
    """
    In-memory, versioned registry of deterministic civic response playbooks.
    Ensures:
    - Zero generative LLM hallucination.
    - Deterministic matching against evidence signals.
    - Clear epistemic distinction between CVKI recommendations and official government SOPs.
    """

    def __init__(self):
        self._playbooks: dict[str, ActionPlaybook] = {}
        self._load_default_playbooks()

    def register(self, playbook: ActionPlaybook) -> None:
        """Registers or updates a versioned playbook."""
        if not playbook.playbook_id:
            raise ValueError("Playbook must have a valid non-empty playbook_id.")
        self._playbooks[playbook.playbook_id] = playbook
        logger.info("Registered civic playbook '%s' (version %s).", playbook.playbook_id, playbook.version)

    def get_playbook(self, playbook_id: str) -> Optional[ActionPlaybook]:
        """Retrieves a playbook by its unique ID."""
        return self._playbooks.get(playbook_id)

    def list_playbooks(self, enabled_only: bool = True) -> list[ActionPlaybook]:
        """Lists all registered playbooks."""
        playbooks = list(self._playbooks.values())
        if enabled_only:
            playbooks = [pb for pb in playbooks if pb.enabled]
        return playbooks

    def match_playbooks(
        self,
        issue_category: IssueCategory,
        has_cv_detection: bool = False,
        priority_level: Optional[str] = None,
        is_recurrent: bool = False,
        has_rain_context: bool = False,
        alignment_score: Optional[float] = None,
    ) -> list[PlaybookMatchResult]:
        """
        Deterministically matches complaint context against all active playbooks.
        Evaluates trigger conditions and evidence requirements.
        """
        results: list[PlaybookMatchResult] = []

        for pb in self.list_playbooks(enabled_only=True):
            tc = pb.trigger_conditions
            # 1. Category check
            if issue_category not in tc.allowed_categories and IssueCategory.UNKNOWN not in tc.allowed_categories:
                continue

            match_reasons: list[str] = []
            missing_evidence: list[str] = []
            score = 0.5  # Base category match score

            match_reasons.append(f"Issue category '{issue_category.value}' matches playbook category filter.")

            # 2. Priority check
            if tc.min_priority:
                if priority_level and priority_level <= tc.min_priority:  # e.g. "P1" <= "P2"
                    match_reasons.append(f"Priority tier '{priority_level}' satisfies condition (min '{tc.min_priority}').")
                    score += 0.2
                else:
                    if not priority_level:
                        missing_evidence.append("priority_analysis")

            # 3. CV detection check
            if tc.requires_cv_detection and not has_cv_detection:
                missing_evidence.append("cv_visual_detection")
                continue  # Mandatory trigger condition not met
            elif has_cv_detection:
                match_reasons.append("Visual defect observation confirmed by computer vision detection.")
                score += 0.2

            # 4. Rain/weather context
            if tc.requires_rain_context and not has_rain_context:
                continue
            elif has_rain_context:
                match_reasons.append("Environmental precipitation context present, amplifying operational urgency.")
                score += 0.1

            # 5. Recurrence
            if is_recurrent:
                match_reasons.append("Historical defect recurrence noted at this location.")
                score += 0.1

            # 6. Alignment score
            if tc.min_alignment_score is not None:
                if alignment_score is not None and alignment_score < tc.min_alignment_score:
                    missing_evidence.append("high_confidence_cross_modal_alignment")

            # 7. Check mandatory evidence requirements
            for req in pb.evidence_requirements.mandatory_evidence:
                if req == "cv_detection" and not has_cv_detection:
                    missing_evidence.append("mandatory:cv_detection")
                elif req == "issue_category" and issue_category == IssueCategory.UNKNOWN:
                    missing_evidence.append("mandatory:issue_category")

            results.append(
                PlaybookMatchResult(
                    playbook_id=pb.playbook_id,
                    playbook_version=pb.version,
                    matched=True,
                    match_score=min(1.0, round(score, 2)),
                    match_reasons=match_reasons,
                    missing_evidence=missing_evidence,
                    recommended_actions=pb.recommended_actions,
                    mitigation_actions=pb.mitigation_actions,
                    prohibited_assumptions=pb.prohibited_assumptions,
                    inspection_checkpoints=pb.evidence_requirements.inspection_checkpoints,
                    uncertainty_notes=[
                        f"Missing recommended evidence: {item}" for item in missing_evidence
                    ],
                )
            )

        # Sort by match score descending
        results.sort(key=lambda x: x.match_score, reverse=True)
        return results

    def _load_default_playbooks(self) -> None:
        """Populates the default built-in civic action playbooks."""
        now = datetime.now(timezone.utc)

        # 1. Open/Damaged Manhole Safety Playbook
        manhole_pb = ActionPlaybook(
            playbook_id="PB-MANHOLE-SAFETY-V1",
            version="1.0.0",
            title="Open / Damaged Manhole Physical Triage & Hazard Mitigation",
            description=(
                "Operational guidelines for verifying aperture dimensions, preventing pedestrian/vehicular "
                "accidents, and coordinating cover replacement without premature utility attribution."
            ),
            issue_categories=[IssueCategory.OPEN_DAMAGED_MANHOLE],
            trigger_conditions=PlaybookTriggerConditions(
                allowed_categories=[IssueCategory.OPEN_DAMAGED_MANHOLE],
                min_priority="P3",
            ),
            evidence_requirements=PlaybookEvidenceRequirements(
                mandatory_evidence=["issue_category"],
                recommended_evidence=["cv_detection", "location_context"],
                inspection_checkpoints=[
                    "Verify rim seating and structural frame cracking",
                    "Measure aperture diameter and depth to silt/water line",
                    "Document adjacent pavement depression or subsidence",
                ],
            ),
            recommended_actions=[
                PlaybookActionItem(
                    action_id="ACT-MANHOLE-INSPECT",
                    action_type=ActionCategory.INSPECT,
                    title="Immediate Physical Site Inspection",
                    description=(
                        "Dispatch certified field inspector to verify location, aperture clearance, and frame condition."
                    ),
                    urgency_level=ActionUrgency.IMMEDIATE,
                    target_role="field_inspector",
                    required_equipment=["measuring_tape", "safety_gloves", "high_vis_vest"],
                ),
                PlaybookActionItem(
                    action_id="ACT-MANHOLE-DOC",
                    action_type=ActionCategory.DOCUMENT,
                    title="Geocoded Evidence Documentation",
                    description=(
                        "Capture clear photographs from two opposing roadway perspectives showing aperture relative to road curb."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="field_inspector",
                    required_equipment=["camera_or_mobile_device"],
                ),
                PlaybookActionItem(
                    action_id="ACT-MANHOLE-REPAIR-PREP",
                    action_type=ActionCategory.FOLLOW_UP,
                    title="Coordinate Frame & Cover Procurement",
                    description=(
                        "Verify utility conduit markings (storm, sewer, electric, telecom) to route cover replacement to responsible agency."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="authority_officer",
                ),
            ],
            mitigation_actions=[
                PlaybookActionItem(
                    action_id="ACT-MANHOLE-BARRICADE",
                    action_type=ActionCategory.MITIGATE,
                    title="Erect Immediate Safety Barricade / Cone",
                    description=(
                        "Place high-visibility physical warning barricade or reflective safety cones around open aperture to prevent vehicular damage or pedestrian injury."
                    ),
                    urgency_level=ActionUrgency.IMMEDIATE,
                    target_role="maintenance_crew",
                    required_equipment=["reflective_cones", "caution_tape", "nighttime_marker"],
                ),
            ],
            prohibited_assumptions=[
                "Do not assume manhole cover was stolen without physical on-site evidence.",
                "Do not assume municipal sewer ownership without verifying utility markings on the frame or adjacent conduit.",
                "Do not mark resolved based solely on temporary barricade placement without verified permanent lid installation.",
            ],
            escalation_guidance="If manhole is situated in active high-speed traffic lane and unbarricaded for > 4 hours, initiate urgent supervisor notification.",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        self.register(manhole_pb)

        # 2. Road Waterlogging & Drainage Obstruction Playbook
        water_pb = ActionPlaybook(
            playbook_id="PB-WATERLOGGING-DRAIN-V1",
            version="1.0.0",
            title="Road Waterlogging & Drainage Obstruction Playbook",
            description=(
                "Guidelines for evaluating standing water depth, clearing blocked catch basins, and evaluating temporary "
                "dewatering pumps while preserving causality boundaries."
            ),
            issue_categories=[IssueCategory.ROAD_WATERLOGGING],
            trigger_conditions=PlaybookTriggerConditions(
                allowed_categories=[IssueCategory.ROAD_WATERLOGGING],
                min_priority="P4",
            ),
            evidence_requirements=PlaybookEvidenceRequirements(
                mandatory_evidence=["issue_category"],
                recommended_evidence=["location_context", "weather_context"],
                inspection_checkpoints=[
                    "Estimate maximum standing water depth along curb line",
                    "Inspect roadside inlet grates for silt, plastic, or debris blockage",
                    "Examine outfall discharge point for hydraulic backwater",
                ],
            ),
            recommended_actions=[
                PlaybookActionItem(
                    action_id="ACT-WATER-INSPECT",
                    action_type=ActionCategory.INSPECT,
                    title="Drainage Catch Basin Assessment",
                    description=(
                        "Inspect curb inlets within 50m upstream and downstream of waterlogged area for solid waste accumulation."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="field_inspector",
                    required_equipment=["depth_gauge", "grate_lifter"],
                ),
                PlaybookActionItem(
                    action_id="ACT-WATER-CLEAR",
                    action_type=ActionCategory.MITIGATE,
                    title="Manual Inlet Debris De-silting",
                    description=(
                        "Clear accumulated surface leaves and plastic debris from storm grate openings to restore gravity inflow."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="maintenance_crew",
                    required_equipment=["rake", "debris_bags", "protective_boots"],
                ),
                PlaybookActionItem(
                    action_id="ACT-WATER-PUMP-EVAL",
                    action_type=ActionCategory.FOLLOW_UP,
                    title="Mobile Dewatering Pump Evaluation",
                    description=(
                        "If ponding exceeds 20cm depth and natural gravity drainage is blocked, evaluate staging a portable diesel dewatering pump."
                    ),
                    urgency_level=ActionUrgency.ADVISORY,
                    target_role="authority_officer",
                ),
            ],
            mitigation_actions=[
                PlaybookActionItem(
                    action_id="ACT-WATER-TRAFFIC-SIGN",
                    action_type=ActionCategory.MITIGATE,
                    title="Deploy Waterlogging Caution Boards",
                    description=(
                        "Place temporary caution signs advising motorists to reduce speed through standing water."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="maintenance_crew",
                    required_equipment=["water_caution_board"],
                ),
            ],
            prohibited_assumptions=[
                "Do not assume waterlogging will recede naturally without checking catch basin discharge.",
                "Do not infer rainfall alone caused ponding without assessing road camber and structural drainage capacity.",
            ],
            escalation_guidance="If standing water enters residential premises or submerges electrical feeder pillar, escalate immediately to emergency drainage cell.",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        self.register(water_pb)

        # 3. Damaged / Missing Road Sign Playbook
        sign_pb = ActionPlaybook(
            playbook_id="PB-ROAD-SIGN-HAZARD-V1",
            version="1.0.0",
            title="Road Sign Structural & Visibility Triage Playbook",
            description=(
                "Guidelines for assessing missing or damaged regulatory/cautionary signs, post vertical stability, "
                "and visibility obstructions."
            ),
            issue_categories=[IssueCategory.DAMAGED_MISSING_ROAD_SIGN],
            trigger_conditions=PlaybookTriggerConditions(
                allowed_categories=[IssueCategory.DAMAGED_MISSING_ROAD_SIGN],
            ),
            evidence_requirements=PlaybookEvidenceRequirements(
                mandatory_evidence=["issue_category"],
                recommended_evidence=["cv_detection"],
                inspection_checkpoints=[
                    "Check pole vertical deflection and base weld integrity",
                    "Verify retro-reflective sheeting condition and graffiti damage",
                    "Document vegetation or commercial banner visual occlusion",
                ],
            ),
            recommended_actions=[
                PlaybookActionItem(
                    action_id="ACT-SIGN-INSPECT",
                    action_type=ActionCategory.INSPECT,
                    title="Physical Post & Foundation Stability Check",
                    description=(
                        "Inspect concrete base and post bolts to determine whether the post is loose or in danger of falling."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="field_inspector",
                ),
                PlaybookActionItem(
                    action_id="ACT-SIGN-VISIBILITY-DOC",
                    action_type=ActionCategory.DOCUMENT,
                    title="Vehicle Approach Visibility Documentation",
                    description=(
                        "Photograph sign from 50m and 20m approach distances to document driver sightlines."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="field_inspector",
                ),
                PlaybookActionItem(
                    action_id="ACT-SIGN-FABRICATION-ORDER",
                    action_type=ActionCategory.FOLLOW_UP,
                    title="Initiate Sign Replacement Requisition",
                    description=(
                        "Identify required standard retro-reflective sign plate specifications for replacement order."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="authority_officer",
                ),
            ],
            mitigation_actions=[
                PlaybookActionItem(
                    action_id="ACT-SIGN-PRUNE",
                    action_type=ActionCategory.MITIGATE,
                    title="Clear Immediate Sightline Obstructions",
                    description=(
                        "Trim obstructing tree branches or remove unauthorized banners obscuring the traffic sign face."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="maintenance_crew",
                    required_equipment=["pruning_shears"],
                ),
            ],
            prohibited_assumptions=[
                "Do not assume missing sign presents zero traffic hazard without evaluating intersection and speed limit context.",
                "Do not assume bent pole can be bent back without checking structural metal fatigue.",
            ],
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        self.register(sign_pb)

        # 4. Generic Civic Defect Playbook
        generic_pb = ActionPlaybook(
            playbook_id="PB-GENERIC-CIVIC-V1",
            version="1.0.0",
            title="General Civic Defect Preliminary Inspection Playbook",
            description=(
                "Standard initial verification protocol for unclassified or miscellaneous civic infrastructure reports."
            ),
            issue_categories=[IssueCategory.OTHER_CIVIC_ISSUE, IssueCategory.UNKNOWN],
            trigger_conditions=PlaybookTriggerConditions(
                allowed_categories=[IssueCategory.OTHER_CIVIC_ISSUE, IssueCategory.UNKNOWN],
            ),
            evidence_requirements=PlaybookEvidenceRequirements(
                mandatory_evidence=["issue_category"],
                recommended_evidence=["location_context"],
                inspection_checkpoints=[
                    "Confirm physical existence of reported condition",
                    "Record prominent local street landmark",
                    "Assess whether issue falls within municipal jurisdiction",
                ],
            ),
            recommended_actions=[
                PlaybookActionItem(
                    action_id="ACT-GENERIC-VERIFY",
                    action_type=ActionCategory.INSPECT,
                    title="Initial Field Walkthrough Verification",
                    description=(
                        "Verify reported defect location and determine appropriate municipal engineering discipline."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="field_inspector",
                ),
                PlaybookActionItem(
                    action_id="ACT-GENERIC-DOC",
                    action_type=ActionCategory.DOCUMENT,
                    title="Multi-Angle Photographic Evidence Capture",
                    description=(
                        "Photograph defect with wide-angle context showing road boundary markers."
                    ),
                    urgency_level=ActionUrgency.STANDARD,
                    target_role="field_inspector",
                ),
            ],
            prohibited_assumptions=[
                "Do not assume an unclassified report is spurious without completing a field spot-check.",
            ],
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        self.register(generic_pb)


action_playbook_registry = ActionPlaybookRegistry()


def get_action_playbook_registry() -> ActionPlaybookRegistry:
    """Returns the singleton instance of ActionPlaybookRegistry."""
    return action_playbook_registry
