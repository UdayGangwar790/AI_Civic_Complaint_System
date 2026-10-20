"""
CVKI - Civic Vision & Knowledge Intelligence
Module 10.6: Decision Provenance & Knowledge Graph Projection Service
"""

from datetime import datetime, timezone
import logging
from typing import Any, Optional
import uuid

from app.schemas.decision_support import DecisionSupportResult
from app.schemas.field_inspection import FieldInspectionRecord
from app.schemas.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeNode,
    NodeType,
    RelationType,
    canonical_case_key,
    canonical_decision_key,
    canonical_evidence_key,
    canonical_inspection_key,
    canonical_playbook_key,
    canonical_user_actor_key,
)
from app.schemas.provenance import (
    ClaimType,
    EvidenceRecord,
    SourceType,
    VerificationState,
)
from app.services.knowledge_graph import (
    CivicKnowledgeGraphService,
    get_knowledge_graph_service,
)
from app.services.provenance_engine import (
    EvidenceProvenanceEngine,
    get_provenance_engine,
)

ProvenanceEngine = EvidenceProvenanceEngine
logger = logging.getLogger("cvki.decision_projection")


class DecisionProvenanceKGProjector:
    """
    Projects M10.4 Decision Support Results and M10.5 Field Inspection Records into:
    - M6.4 Cryptographic Provenance Engine
    - M6.5 Unified Civic Knowledge Graph

    Enforces strict architectural boundaries:
    - Does NOT create a second graph or second provenance engine.
    - Does NOT mutate complaint case lifecycle state (never marks resolved or closed).
    - Preserves audit versioning (historical decisions are never overwritten).
    - Propagates invalidation when supporting evidence is compromised.
    """

    def __init__(
        self,
        provenance_engine: Optional[ProvenanceEngine] = None,
        kg_service: Optional[CivicKnowledgeGraphService] = None,
    ):
        self._prov_engine_override = provenance_engine
        self._kg_service_override = kg_service

    @property
    def _provenance_engine(self) -> ProvenanceEngine:
        return self._prov_engine_override or get_provenance_engine()

    @property
    def _kg_service(self) -> CivicKnowledgeGraphService:
        return self._kg_service_override or get_knowledge_graph_service()

    def project_decision_recommendation(
        self,
        case_reference: str,
        decision: DecisionSupportResult,
        supporting_evidence_ids: Optional[list[str]] = None,
    ) -> tuple[EvidenceRecord, list[KnowledgeNode], list[KnowledgeEdge]]:
        """
        Projects an operational decision support recommendation into provenance and knowledge graph.
        """
        now = datetime.now(timezone.utc)
        supp_ids = list(supporting_evidence_ids or [])

        # 1. M6.4 Provenance Record
        claim_val = {
            "recommendation_id": decision.recommendation_id,
            "evidence_quality": decision.evidence_quality.value,
            "matched_playbooks": decision.matched_playbooks,
            "action_count": len(decision.recommended_actions),
            "decision_version": decision.decision_version,
            "human_review_required": decision.human_review_required,
        }

        # Check existing version history for idempotency / version bump
        history = self._provenance_engine.repository.find_history(
            case_reference, ClaimType.OPERATIONAL_DECISION_RECOMMENDATION
        )
        version = len(history) + 1

        prov_record = self._provenance_engine.build_evidence_record(
            case_reference=case_reference,
            claim_type=ClaimType.OPERATIONAL_DECISION_RECOMMENDATION,
            source="CVKI Decision Support Engine",
            source_type=SourceType.SYSTEM_DERIVED,
            explanation=decision.explanation,
            verification_state=VerificationState.SYSTEM_DERIVED,
            version=version,
            claim_value=claim_val,
            metadata={
                "recommendation_id": decision.recommendation_id,
                "epistemic_state": decision.epistemic_state.value,
                "supporting_evidence_ids": supp_ids,
                "claim_value": claim_val,
            },
        )

        nodes: list[KnowledgeNode] = []
        edges: list[KnowledgeEdge] = []

        # 2. M6.5 Knowledge Graph Projection
        # A. Case Node
        case_key = canonical_case_key(case_reference)
        case_node = self._kg_service._ensure_node(
            node_type=NodeType.CASE,
            canonical_key=case_key,
            display_name=f"Case {case_reference}",
            case_reference=case_reference,
        )
        nodes.append(case_node)

        # B. Decision Recommendation Node
        dec_key = canonical_decision_key(decision.recommendation_id)
        dec_node = self._kg_service._ensure_node(
            node_type=NodeType.DECISION_RECOMMENDATION,
            canonical_key=dec_key,
            display_name=f"Decision Rec: {decision.recommendation_id[:8]}",
            case_reference=case_reference,
            metadata={
                "recommendation_id": decision.recommendation_id,
                "evidence_quality": decision.evidence_quality.value,
                "decision_version": decision.decision_version,
                "status": "active",
                "human_review_required": decision.human_review_required,
                "provenance_id": prov_record.evidence_id,
                "generated_at": decision.generated_at.isoformat(),
            },
        )
        nodes.append(dec_node)

        # Edge: Case -> HAS_ESCALATION_DECISION -> Decision Recommendation
        e_case_dec = self._kg_service._ensure_edge(
            from_node=case_node,
            to_node=dec_node,
            relation_type=RelationType.HAS_ESCALATION_DECISION,
            verification_state=VerificationState.SYSTEM_DERIVED,
            evidence_ids=[prov_record.evidence_id],
            case_reference=case_reference,
            explanation=f"Case evaluated by Decision Support Engine v{decision.decision_version}",
        )
        edges.append(e_case_dec)

        # C. Playbook Nodes & RECOMMENDS_PLAYBOOK Edges
        for pb_entry in decision.matched_playbooks:
            pb_id = pb_entry.split()[0]  # Extracts ID (e.g. PB-MANHOLE-SAFETY-V1)
            pb_key = canonical_playbook_key(pb_id)
            pb_node = self._kg_service._ensure_node(
                node_type=NodeType.OPERATIONAL_PLAYBOOK,
                canonical_key=pb_key,
                display_name=f"Playbook: {pb_id}",
                case_reference=case_reference,
                metadata={"playbook_id": pb_id},
            )
            nodes.append(pb_node)

            e_rec_pb = self._kg_service._ensure_edge(
                from_node=dec_node,
                to_node=pb_node,
                relation_type=RelationType.RECOMMENDS_PLAYBOOK,
                verification_state=VerificationState.SYSTEM_DERIVED,
                case_reference=case_reference,
                explanation=f"Decision recommendation matched operational playbook {pb_id}",
            )
            edges.append(e_rec_pb)

        # D. Supporting Evidence Edges
        for ev_id in supp_ids:
            ev_key = canonical_evidence_key(ev_id)
            ev_node = self._kg_service.repository.get_node_by_key(ev_key)
            if ev_node:
                e_supp = self._kg_service._ensure_edge(
                    from_node=dec_node,
                    to_node=ev_node,
                    relation_type=RelationType.DECISION_SUPPORTED_BY,
                    verification_state=VerificationState.SYSTEM_DERIVED,
                    evidence_ids=[ev_id],
                    case_reference=case_reference,
                    explanation=f"Decision recommendation justified by evidence {ev_id}",
                )
                edges.append(e_supp)

        logger.info(
            "Projected decision %s for case %s into KG (%d nodes, %d edges, prov: %s)",
            decision.recommendation_id,
            case_reference,
            len(nodes),
            len(edges),
            prov_record.evidence_id,
        )

        return prov_record, nodes, edges

    def project_field_inspection(
        self,
        record: FieldInspectionRecord,
    ) -> tuple[EvidenceRecord, list[KnowledgeNode], list[KnowledgeEdge]]:
        """
        Projects an executed field inspection and audit result into provenance and knowledge graph.
        """
        now = datetime.now(timezone.utc)
        case_ref = record.case_reference

        # 1. M6.4 Provenance Record
        history = self._provenance_engine.repository.find_history(
            case_ref, ClaimType.FIELD_INSPECTION_AUDIT
        )
        version = len(history) + 1

        v_state = (
            VerificationState.PARTIALLY_VERIFIED
            if record.audit_result.outcome.value in ("SUPPORTED", "PARTIALLY_SUPPORTED")
            else VerificationState.NOT_VERIFIED
        )

        prov_record = self._provenance_engine.build_evidence_record(
            case_reference=case_ref,
            claim_type=ClaimType.FIELD_INSPECTION_AUDIT,
            source=f"Inspector {record.inspector_id}",
            source_type=SourceType.AUTHORITY_UPDATE,
            explanation=record.audit_result.audit_explanation,
            verification_state=v_state,
            version=version,
            claim_value={
                "inspection_id": record.inspection_id,
                "protocol_id": record.protocol_id,
                "audit_outcome": record.audit_result.outcome.value,
                "completeness": record.completeness.value,
                "geofence_result": record.geofence_result.value,
            },
            metadata={
                "inspection_id": record.inspection_id,
                "inspector_id": record.inspector_id,
                "evidence_items": record.evidence_items,
                "claim_value": {
                    "inspection_id": record.inspection_id,
                    "protocol_id": record.protocol_id,
                    "audit_outcome": record.audit_result.outcome.value,
                    "completeness": record.completeness.value,
                    "geofence_result": record.geofence_result.value,
                },
            },
        )

        nodes: list[KnowledgeNode] = []
        edges: list[KnowledgeEdge] = []

        # 2. M6.5 Knowledge Graph Projection
        # A. Case Node
        case_key = canonical_case_key(case_ref)
        case_node = self._kg_service._ensure_node(
            node_type=NodeType.CASE,
            canonical_key=case_key,
            display_name=f"Case {case_ref}",
            case_reference=case_ref,
        )
        nodes.append(case_node)

        # B. Field Inspection Node
        insp_key = canonical_inspection_key(record.inspection_id)
        insp_node = self._kg_service._ensure_node(
            node_type=NodeType.FIELD_INSPECTION,
            canonical_key=insp_key,
            display_name=f"Field Inspection: {record.inspection_id}",
            case_reference=case_ref,
            metadata={
                "inspection_id": record.inspection_id,
                "protocol_id": record.protocol_id,
                "protocol_version": record.protocol_version,
                "inspector_id": record.inspector_id,
                "audit_outcome": record.audit_result.outcome.value,
                "completeness": record.completeness.value,
                "geofence_result": record.geofence_result.value,
                "provenance_id": prov_record.evidence_id,
            },
        )
        nodes.append(insp_node)

        # Edge: Case -> RELATED_TO -> Field Inspection
        e_case_insp = self._kg_service._ensure_edge(
            from_node=case_node,
            to_node=insp_node,
            relation_type=RelationType.RELATED_TO,
            verification_state=v_state,
            evidence_ids=[prov_record.evidence_id],
            case_reference=case_ref,
            explanation=f"Field inspection executed by inspector {record.inspector_id}",
        )
        edges.append(e_case_insp)

        # C. Inspector User Actor Node & ASSIGNED_TO Edge
        actor_key = canonical_user_actor_key(record.inspector_id)
        actor_node = self._kg_service._ensure_node(
            node_type=NodeType.USER_ACTOR,
            canonical_key=actor_key,
            display_name=f"Inspector: {record.inspector_id}",
            case_reference=case_ref,
        )
        nodes.append(actor_node)

        e_actor_insp = self._kg_service._ensure_edge(
            from_node=actor_node,
            to_node=insp_node,
            relation_type=RelationType.ASSIGNED_TO,
            verification_state=VerificationState.VERIFIED,
            case_reference=case_ref,
            explanation=f"Inspector {record.inspector_id} recorded on-site inspection",
        )
        edges.append(e_actor_insp)

        # D. Playbook INSPECTION_SATISFIES Edge
        if record.protocol_id:
            pb_key = canonical_playbook_key(record.protocol_id.replace("PROTOCOL", "PB"))
            pb_node = self._kg_service.repository.get_node_by_key(pb_key)
            if pb_node:
                e_insp_pb = self._kg_service._ensure_edge(
                    from_node=insp_node,
                    to_node=pb_node,
                    relation_type=RelationType.INSPECTION_SATISFIES,
                    verification_state=v_state,
                    case_reference=case_ref,
                    explanation=f"Field inspection verified inspection checkpoints of {pb_node.display_name}",
                )
                edges.append(e_insp_pb)

        return prov_record, nodes, edges

    def handle_evidence_invalidation(
        self,
        invalidated_evidence_id: str,
        case_reference: str,
        reason: str = "Supporting evidence invalidated",
    ) -> list[str]:
        """
        Propagates evidence invalidation to any decision recommendation nodes supported by it.
        Downgrades decision node status to 'stale' without silent data corruption.
        """
        # Invalidate in provenance engine
        self._provenance_engine.repository.invalidate(invalidated_evidence_id, reason)

        affected_decision_keys: list[str] = []

        # Find edges from decision recommendations to this evidence
        ev_key = canonical_evidence_key(invalidated_evidence_id)
        edges_to_ev = self._kg_service.repository.find_edges_to(ev_key)

        for edge in edges_to_ev:
            if edge.relation_type == RelationType.DECISION_SUPPORTED_BY:
                # Downgrade the decision recommendation node
                dec_node = self._kg_service.repository.get_node_by_key(edge.from_node)
                if dec_node:
                    dec_node.metadata["status"] = "stale"
                    dec_node.metadata["stale_reason"] = f"Supporting evidence {invalidated_evidence_id} invalidated: {reason}"
                    dec_node.updated_at = datetime.now(timezone.utc)
                    self._kg_service.repository.save_node(dec_node)
                    affected_decision_keys.append(dec_node.canonical_key)

                # Update edge verification state to STALE
                edge.verification_state = VerificationState.STALE
                self._kg_service.repository.save_edge(edge)

        logger.warning(
            "Propagated invalidation for evidence %s on case %s (Affected decisions: %s)",
            invalidated_evidence_id,
            case_reference,
            affected_decision_keys,
        )

        return affected_decision_keys

    def get_case_decision_provenance(self, case_reference: str) -> list[EvidenceRecord]:
        """Retrieves all decision and inspection provenance records for a case."""
        records: list[EvidenceRecord] = []
        records.extend(
            self._provenance_engine.repository.find_history(
                case_reference, ClaimType.OPERATIONAL_DECISION_RECOMMENDATION
            )
        )
        records.extend(
            self._provenance_engine.repository.find_history(
                case_reference, ClaimType.FIELD_INSPECTION_AUDIT
            )
        )
        return records

    def get_case_decision_subgraph(self, case_reference: str) -> dict[str, list[dict[str, Any]]]:
        """Returns the decision support and inspection subgraph for a case."""
        case_nodes = self._kg_service.repository.find_nodes_by_case(case_reference)
        case_edges = self._kg_service.repository.find_edges_by_case(case_reference)

        # Filter to decision/inspection/playbook nodes and edges
        target_node_types = {
            NodeType.CASE,
            NodeType.DECISION_RECOMMENDATION,
            NodeType.OPERATIONAL_PLAYBOOK,
            NodeType.FIELD_INSPECTION,
            NodeType.USER_ACTOR,
            NodeType.EVIDENCE,
        }

        filtered_nodes = [
            n.model_dump(mode="json")
            for n in case_nodes
            if n.node_type in target_node_types
        ]
        filtered_edges = [
            e.model_dump(mode="json")
            for e in case_edges
        ]

        return {
            "case_reference": case_reference,
            "nodes": filtered_nodes,
            "edges": filtered_edges,
        }


decision_projector = DecisionProvenanceKGProjector()


def get_decision_projector() -> DecisionProvenanceKGProjector:
    return decision_projector
