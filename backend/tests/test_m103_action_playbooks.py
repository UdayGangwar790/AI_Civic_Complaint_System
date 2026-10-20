"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.3: Civic Action Playbook Knowledge Base & Schema Tests
"""

import pytest
from app.schemas.action_playbook import (
    ActionCategory,
    ActionPlaybook,
    ActionUrgency,
    PlaybookActionItem,
    PlaybookEvidenceRequirements,
    PlaybookMatchResult,
    PlaybookTriggerConditions,
)
from app.services.action_playbook import (
    ActionPlaybookRegistry,
    get_action_playbook_registry,
)
from app.services.multimodal.contracts import IssueCategory


def test_1_schema_validation():
    """Verify validation and default values for ActionPlaybook schemas."""
    item = PlaybookActionItem(
        action_id="ACT-001",
        action_type=ActionCategory.INSPECT,
        title="Physical Site Inspection",
        description="Verify condition on site",
        urgency_level=ActionUrgency.IMMEDIATE,
        target_role="field_inspector",
        required_equipment=["flashlight", "measuring_tape"],
    )
    assert item.action_id == "ACT-001"
    assert item.urgency_level == ActionUrgency.IMMEDIATE
    assert item.epistemic_tag == "CVKI recommended action"

    tc = PlaybookTriggerConditions(
        allowed_categories=[IssueCategory.OPEN_DAMAGED_MANHOLE],
        min_priority="P2",
    )
    assert tc.allowed_categories == [IssueCategory.OPEN_DAMAGED_MANHOLE]
    assert tc.min_priority == "P2"

    er = PlaybookEvidenceRequirements(
        mandatory_evidence=["issue_category"],
        recommended_evidence=["cv_detection"],
        inspection_checkpoints=["Check structural integrity"],
    )
    assert er.mandatory_evidence == ["issue_category"]

    pb = ActionPlaybook(
        playbook_id="PB-TEST-V1",
        version="1.0.0",
        title="Test Playbook",
        description="A test playbook for validation",
        issue_categories=[IssueCategory.OPEN_DAMAGED_MANHOLE],
        trigger_conditions=tc,
        evidence_requirements=er,
        recommended_actions=[item],
        prohibited_assumptions=["Do not assume resolved without verification"],
    )
    assert pb.playbook_id == "PB-TEST-V1"
    assert pb.enabled is True
    assert len(pb.recommended_actions) == 1
    assert len(pb.prohibited_assumptions) == 1


def test_2_builtin_playbooks_loaded():
    """Verify built-in playbooks load correctly with unique IDs."""
    reg = ActionPlaybookRegistry()
    playbooks = reg.list_playbooks()
    assert len(playbooks) >= 4

    ids = [pb.playbook_id for pb in playbooks]
    assert len(ids) == len(set(ids)), "Playbook IDs must be unique"
    assert "PB-MANHOLE-SAFETY-V1" in ids
    assert "PB-WATERLOGGING-DRAIN-V1" in ids
    assert "PB-ROAD-SIGN-HAZARD-V1" in ids
    assert "PB-GENERIC-CIVIC-V1" in ids


def test_3_issue_category_matching():
    """Verify open damaged manhole category matches PB-MANHOLE-SAFETY-V1."""
    reg = ActionPlaybookRegistry()
    matches = reg.match_playbooks(issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)
    assert len(matches) > 0
    top = matches[0]
    assert top.playbook_id == "PB-MANHOLE-SAFETY-V1"
    assert top.matched is True
    assert top.match_score >= 0.5


def test_4_waterlogging_matching():
    """Verify waterlogging category matches PB-WATERLOGGING-DRAIN-V1."""
    reg = ActionPlaybookRegistry()
    matches = reg.match_playbooks(issue_category=IssueCategory.ROAD_WATERLOGGING)
    assert len(matches) > 0
    top = matches[0]
    assert top.playbook_id == "PB-WATERLOGGING-DRAIN-V1"
    assert top.matched is True


def test_5_road_sign_matching():
    """Verify road sign category matches PB-ROAD-SIGN-HAZARD-V1."""
    reg = ActionPlaybookRegistry()
    matches = reg.match_playbooks(issue_category=IssueCategory.DAMAGED_MISSING_ROAD_SIGN)
    assert len(matches) > 0
    top = matches[0]
    assert top.playbook_id == "PB-ROAD-SIGN-HAZARD-V1"
    assert top.matched is True


def test_6_generic_fallback_matching():
    """Verify unclassified/other categories match generic playbook."""
    reg = ActionPlaybookRegistry()
    matches = reg.match_playbooks(issue_category=IssueCategory.OTHER_CIVIC_ISSUE)
    assert len(matches) > 0
    top = matches[0]
    assert top.playbook_id == "PB-GENERIC-CIVIC-V1"


def test_7_priority_boost():
    """Verify higher priority (e.g. P1) increases match score."""
    reg = ActionPlaybookRegistry()
    base_matches = reg.match_playbooks(
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        priority_level=None,
    )
    boosted_matches = reg.match_playbooks(
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        priority_level="P1",
    )
    assert boosted_matches[0].match_score > base_matches[0].match_score
    assert any("Priority tier 'P1'" in r for r in boosted_matches[0].match_reasons)


def test_8_cv_detection_boost():
    """Verify presence of CV detection observation boosts match score."""
    reg = ActionPlaybookRegistry()
    base_matches = reg.match_playbooks(
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        has_cv_detection=False,
    )
    cv_matches = reg.match_playbooks(
        issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE,
        has_cv_detection=True,
    )
    assert cv_matches[0].match_score > base_matches[0].match_score
    assert any("Visual defect observation confirmed" in r for r in cv_matches[0].match_reasons)


def test_9_rain_context_boost():
    """Verify rain context boosts score for waterlogging playbook."""
    reg = ActionPlaybookRegistry()
    base_matches = reg.match_playbooks(
        issue_category=IssueCategory.ROAD_WATERLOGGING,
        has_rain_context=False,
    )
    rain_matches = reg.match_playbooks(
        issue_category=IssueCategory.ROAD_WATERLOGGING,
        has_rain_context=True,
    )
    assert rain_matches[0].match_score > base_matches[0].match_score
    assert any("precipitation context" in r for r in rain_matches[0].match_reasons)


def test_10_disabled_playbook_ignored():
    """Verify disabled playbook is excluded from active matching and listing."""
    reg = ActionPlaybookRegistry()
    pb = reg.get_playbook("PB-MANHOLE-SAFETY-V1")
    assert pb is not None
    pb.enabled = False

    matches = reg.match_playbooks(issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)
    matched_ids = [m.playbook_id for m in matches]
    assert "PB-MANHOLE-SAFETY-V1" not in matched_ids

    # Restore
    pb.enabled = True


def test_11_prohibited_assumptions_present():
    """Verify matched playbooks convey explicit cognitive caveats."""
    reg = ActionPlaybookRegistry()
    matches = reg.match_playbooks(issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)
    top = matches[0]
    assert len(top.prohibited_assumptions) > 0
    assert any("stolen" in a.lower() for a in top.prohibited_assumptions)


def test_12_inspection_checkpoints_present():
    """Verify matched playbooks provide physical on-site inspection criteria."""
    reg = ActionPlaybookRegistry()
    matches = reg.match_playbooks(issue_category=IssueCategory.OPEN_DAMAGED_MANHOLE)
    top = matches[0]
    assert len(top.inspection_checkpoints) > 0
    assert any("aperture" in c.lower() for c in top.inspection_checkpoints)


def test_13_custom_playbook_registration():
    """Verify registration and matching of a newly added custom civic playbook."""
    reg = ActionPlaybookRegistry()
    custom_pb = ActionPlaybook(
        playbook_id="PB-CUSTOM-STREETLIGHT-V1",
        version="1.0.0",
        title="Streetlight Non-Functional Triage",
        description="Guidelines for streetlight outages",
        issue_categories=[IssueCategory.OTHER_CIVIC_ISSUE],
        trigger_conditions=PlaybookTriggerConditions(
            allowed_categories=[IssueCategory.OTHER_CIVIC_ISSUE],
        ),
        evidence_requirements=PlaybookEvidenceRequirements(
            mandatory_evidence=["issue_category"],
        ),
        recommended_actions=[
            PlaybookActionItem(
                action_id="ACT-LIGHT-TEST",
                action_type=ActionCategory.INSPECT,
                title="Feeder Pillar Electrical Check",
                description="Test voltage at base junction box",
            )
        ],
    )
    reg.register(custom_pb)
    retrieved = reg.get_playbook("PB-CUSTOM-STREETLIGHT-V1")
    assert retrieved is not None
    assert retrieved.title == "Streetlight Non-Functional Triage"


def test_14_empty_id_registration_fails():
    """Verify registering a playbook with an empty ID raises ValueError."""
    reg = ActionPlaybookRegistry()
    with pytest.raises(ValueError):
        reg.register(
            ActionPlaybook(
                playbook_id="",
                title="Invalid",
                description="Invalid",
                issue_categories=[IssueCategory.OTHER_CIVIC_ISSUE],
                trigger_conditions=PlaybookTriggerConditions(
                    allowed_categories=[IssueCategory.OTHER_CIVIC_ISSUE]
                ),
                evidence_requirements=PlaybookEvidenceRequirements(),
                recommended_actions=[],
            )
        )


def test_15_playbook_json_serialization():
    """Verify full Pydantic model serialization and deserialization roundtrip."""
    reg = ActionPlaybookRegistry()
    pb = reg.get_playbook("PB-MANHOLE-SAFETY-V1")
    assert pb is not None

    dumped = pb.model_dump()
    assert isinstance(dumped, dict)
    assert dumped["playbook_id"] == "PB-MANHOLE-SAFETY-V1"

    reconstructed = ActionPlaybook.model_validate(dumped)
    assert reconstructed.playbook_id == pb.playbook_id
    assert len(reconstructed.recommended_actions) == len(pb.recommended_actions)
