from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.provenance import SourceType, VerificationState


class NodeType(str, Enum):
    CIVIC_ISSUE = "civic_issue"
    DETECTION = "detection"
    CASE = "case"
    LOCATION = "location"
    ROAD = "road"
    ROAD_SEGMENT = "road_segment"
    JURISDICTION = "jurisdiction"
    ROAD_OWNER = "road_owner"
    MAINTENANCE_AUTHORITY = "maintenance_authority"
    BUILDER_OR_CONTRACTOR = "builder_or_contractor"
    EVIDENCE = "evidence"
    WEATHER_CONTEXT = "weather_context"
    RAINFALL_CONTEXT = "rainfall_context"
    TRAFFIC_CONTEXT = "traffic_context"
    RECURRENCE_PATTERN = "recurrence_pattern"
    HOTSPOT = "hotspot"
    COMPLAINT = "complaint"
    RESOLUTION = "resolution"
    SOURCE = "source"
    USER_ACTOR = "user_actor"
    GOVERNMENT_SUBMISSION = "government_submission"
    EXTERNAL_CASE = "external_case"
    GOVERNMENT_STATUS = "government_status"
    ESCALATION_DECISION = "escalation_decision"
    RESOLUTION_VERIFICATION = "resolution_verification"
    VERNACULAR_NORMALIZATION = "vernacular_normalization"
    VISUAL_RESOLUTION_AUDIT = "visual_resolution_audit"
    OPERATIONAL_PLAYBOOK = "operational_playbook"
    FIELD_INSPECTION = "field_inspection"
    DECISION_RECOMMENDATION = "decision_recommendation"



class RelationType(str, Enum):
    DETECTED_AS = "DETECTED_AS"
    LOCATED_AT = "LOCATED_AT"
    ON_ROAD = "ON_ROAD"
    ON_ROAD_SEGMENT = "ON_ROAD_SEGMENT"
    WITHIN_JURISDICTION = "WITHIN_JURISDICTION"
    OWNED_BY = "OWNED_BY"
    MAINTAINED_BY = "MAINTAINED_BY"
    BUILT_BY = "BUILT_BY"
    SUPPORTED_BY = "SUPPORTED_BY"
    SOURCED_FROM = "SOURCED_FROM"
    HAS_EXTERNAL_CONTEXT = "HAS_EXTERNAL_CONTEXT"
    HAS_WEATHER_CONTEXT = "HAS_WEATHER_CONTEXT"
    HAS_RAINFALL_CONTEXT = "HAS_RAINFALL_CONTEXT"
    HAS_TRAFFIC_CONTEXT = "HAS_TRAFFIC_CONTEXT"
    RECURRENCE_OF = "RECURRENCE_OF"
    PART_OF_HOTSPOT = "PART_OF_HOTSPOT"
    DUPLICATE_OF = "DUPLICATE_OF"
    RELATED_TO = "RELATED_TO"
    HAS_COMPLAINT = "HAS_COMPLAINT"
    HAS_RESOLUTION = "HAS_RESOLUTION"
    RESOLVED_BY = "RESOLVED_BY"
    ASSIGNED_TO = "ASSIGNED_TO"
    SUBMITTED_TO = "SUBMITTED_TO"
    GENERATED_FROM = "GENERATED_FROM"
    GOVERNMENT_SUBMISSION = "GOVERNMENT_SUBMISSION"
    REFERENCES = "REFERENCES"
    HAS_GOVERNMENT_STATUS = "HAS_GOVERNMENT_STATUS"
    HAS_ESCALATION_DECISION = "HAS_ESCALATION_DECISION"
    HAS_RESOLUTION_VERIFICATION = "HAS_RESOLUTION_VERIFICATION"
    HAS_VERNACULAR_NORMALIZATION = "HAS_VERNACULAR_NORMALIZATION"
    NORMALIZED_AS = "NORMALIZED_AS"
    VISUAL_AUDIT_OF = "VISUAL_AUDIT_OF"
    BEFORE_OBSERVATION = "BEFORE_OBSERVATION"
    AFTER_OBSERVATION = "AFTER_OBSERVATION"
    RECOMMENDS_PLAYBOOK = "RECOMMENDS_PLAYBOOK"
    REQUIRES_INSPECTION = "REQUIRES_INSPECTION"
    INSPECTION_SATISFIES = "INSPECTION_SATISFIES"
    DECISION_SUPPORTED_BY = "DECISION_SUPPORTED_BY"
    DECISION_REQUIRES_EVIDENCE = "DECISION_REQUIRES_EVIDENCE"
    INSPECTION_AUDITS = "INSPECTION_AUDITS"



def normalize_string_key(val: Optional[str]) -> str:
    """Normalizes arbitrary string tokens into a deterministic slug for canonical keys."""
    if not val:
        return "unspecified"
    s = val.strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "_", s)
    return s.strip("_") or "unspecified"


def canonical_case_key(ref_id: str) -> str:
    return f"case:{ref_id.strip()}"


def canonical_road_key(road_name: Optional[str], city: Optional[str] = "") -> str:
    return f"road:{normalize_string_key(road_name)}:{normalize_string_key(city)}"


def canonical_road_segment_key(road_name: Optional[str], segment_id: Optional[str] = "seg_0") -> str:
    return f"road_segment:{normalize_string_key(road_name)}:{normalize_string_key(segment_id)}"


def canonical_authority_key(name: Optional[str]) -> str:
    return f"authority:{normalize_string_key(name)}"


def canonical_jurisdiction_key(name: Optional[str], level: Optional[str] = None) -> str:
    base = f"jurisdiction:{normalize_string_key(name)}"
    if level:
        return f"{base}:{normalize_string_key(level)}"
    return base


def canonical_location_key(lat: float, lon: float, precision: int = 4) -> str:
    # 4 decimals provides ~11m spatial resolution, preventing unstable float matching
    return f"location:{lat:.{precision}f}:{lon:.{precision}f}"


def canonical_issue_key(class_name: Optional[str]) -> str:
    return f"civic_issue:{normalize_string_key(class_name)}"


def canonical_detection_key(ref_id: str, class_name: Optional[str]) -> str:
    return f"detection:{ref_id.strip()}:{normalize_string_key(class_name)}"


def canonical_builder_key(name: Optional[str]) -> str:
    return f"builder:{normalize_string_key(name)}"


def canonical_evidence_key(evidence_id: str) -> str:
    return f"evidence:{evidence_id.strip()}"


def canonical_weather_key(provider: Optional[str], lat: float, lon: float) -> str:
    return f"weather:{normalize_string_key(provider)}:{lat:.2f}:{lon:.2f}"


def canonical_rainfall_key(provider: Optional[str], lat: float, lon: float) -> str:
    return f"rainfall:{normalize_string_key(provider)}:{lat:.2f}:{lon:.2f}"


def canonical_traffic_key(provider: Optional[str], road_key: str) -> str:
    return f"traffic:{normalize_string_key(provider)}:{road_key}"


def canonical_recurrence_key(issue_category: Optional[str], spatial_key: str) -> str:
    return f"recurrence:{normalize_string_key(issue_category)}:{spatial_key}"


def canonical_hotspot_key(issue_category: Optional[str], area_key: str) -> str:
    return f"hotspot:{normalize_string_key(issue_category)}:{normalize_string_key(area_key)}"


def canonical_complaint_key(ref_id: str) -> str:
    return f"complaint:{ref_id.strip()}"


def canonical_resolution_key(ref_id: str) -> str:
    return f"resolution:{ref_id.strip()}"


def canonical_source_key(source_name: Optional[str]) -> str:
    return f"source:{normalize_string_key(source_name)}"


def canonical_user_actor_key(user_id: str) -> str:
    return f"actor:{user_id.strip()}"


def canonical_government_status_key(integration_id: str, government_reference_id: str, status_code: str) -> str:
    return f"gov_status:{normalize_string_key(integration_id)}:{normalize_string_key(government_reference_id)}:{normalize_string_key(status_code)}"


def canonical_escalation_decision_key(cvki_reference_id: str, decision_id: str) -> str:
    return f"escalation:{normalize_string_key(cvki_reference_id)}:{normalize_string_key(decision_id)}"


def canonical_resolution_verification_key(cvki_reference_id: str, verification_id: str) -> str:
    return f"resolution_verification:{normalize_string_key(cvki_reference_id)}:{normalize_string_key(verification_id)}"


def canonical_vernacular_normalization_key(cvki_reference_id: str, norm_id: str) -> str:
    return f"vernacular_norm:{normalize_string_key(cvki_reference_id)}:{normalize_string_key(norm_id)}"


def canonical_visual_audit_key(cvki_reference_id: str, audit_id: str) -> str:
    return f"visual_audit:{normalize_string_key(cvki_reference_id)}:{normalize_string_key(audit_id)}"


def canonical_playbook_key(playbook_id: str) -> str:
    return f"playbook:{normalize_string_key(playbook_id)}"


def canonical_decision_key(recommendation_id: str) -> str:
    return f"decision_rec:{normalize_string_key(recommendation_id)}"


def canonical_inspection_key(inspection_id: str) -> str:
    return f"field_inspection:{normalize_string_key(inspection_id)}"


def canonical_edge_key(from_key: str, relation: Any, to_key: str) -> str:
    rel_str = relation.value if hasattr(relation, "value") else str(relation)
    return f"edge:{from_key}:{rel_str}:{to_key}"


class KnowledgeNode(BaseModel):
    node_id: str
    node_type: NodeType
    canonical_key: str
    display_name: str
    case_references: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeEdge(BaseModel):
    edge_id: str
    canonical_edge_key: str
    from_node: str
    to_node: str
    relation_type: RelationType
    evidence_ids: list[str] = Field(default_factory=list)
    verification_state: VerificationState = VerificationState.PARTIALLY_VERIFIED
    source_type: Optional[SourceType] = None
    case_reference: Optional[str] = None
    explanation: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeGraphSubgraph(BaseModel):
    root_node_key: str
    nodes: list[KnowledgeNode] = Field(default_factory=list)
    edges: list[KnowledgeEdge] = Field(default_factory=list)
    total_nodes: int = 0
    total_edges: int = 0
    max_depth_reached: int = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    limitations: list[str] = Field(default_factory=list)


class RelationshipExplanationResponse(BaseModel):
    edge_id: str
    canonical_edge_key: str
    from_node: KnowledgeNode
    to_node: KnowledgeNode
    relation_type: RelationType
    verification_state: VerificationState
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_records: list[dict[str, Any]] = Field(default_factory=list)
    source: Optional[str] = None
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    explanation: str = ""
    retrieved_at: Optional[datetime] = None
    freshness: str = "fresh"
    limitations: list[str] = Field(default_factory=list)
