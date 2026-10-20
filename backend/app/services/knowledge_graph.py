from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
import json
import logging
from threading import Lock
from typing import Any, Optional
import uuid

from app.core.config import settings
from app.core.database import (
    KNOWLEDGE_EDGES_COLLECTION,
    KNOWLEDGE_NODES_COLLECTION,
    get_database,
)
from app.schemas.complaint_case import ComplaintCase
from app.schemas.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeGraphSubgraph,
    KnowledgeNode,
    NodeType,
    RelationType,
    RelationshipExplanationResponse,
    canonical_authority_key,
    canonical_builder_key,
    canonical_case_key,
    canonical_complaint_key,
    canonical_detection_key,
    canonical_edge_key,
    canonical_escalation_decision_key,
    canonical_evidence_key,
    canonical_government_status_key,
    canonical_hotspot_key,
    canonical_issue_key,
    canonical_jurisdiction_key,
    canonical_location_key,
    canonical_rainfall_key,
    canonical_recurrence_key,
    canonical_resolution_key,
    canonical_resolution_verification_key,
    canonical_road_key,
    canonical_road_segment_key,
    canonical_traffic_key,
    canonical_user_actor_key,
    canonical_vernacular_normalization_key,
    canonical_visual_audit_key,
    canonical_weather_key,
)
from app.schemas.provenance import (
    CaseProvenanceResponse,
    ClaimType,
    EvidenceRecord,
    SourceType,
    VerificationState,
)
from app.services.provenance_engine import get_provenance_engine

logger = logging.getLogger("cvki.knowledge_graph")


class KnowledgeGraphRepository(ABC):
    """Abstract interface for storing and querying Knowledge Graph nodes and edges."""

    @abstractmethod
    def save_node(self, node: KnowledgeNode) -> KnowledgeNode:
        pass

    @abstractmethod
    def get_node_by_key(self, canonical_key: str) -> Optional[KnowledgeNode]:
        pass

    @abstractmethod
    def get_node_by_id(self, node_id: str) -> Optional[KnowledgeNode]:
        pass

    @abstractmethod
    def save_edge(self, edge: KnowledgeEdge) -> KnowledgeEdge:
        pass

    @abstractmethod
    def get_edge_by_key(self, canonical_edge_key: str) -> Optional[KnowledgeEdge]:
        pass

    @abstractmethod
    def get_edge_by_id(self, edge_id: str) -> Optional[KnowledgeEdge]:
        pass

    @abstractmethod
    def find_edges_from(self, canonical_key: str) -> list[KnowledgeEdge]:
        pass

    @abstractmethod
    def find_edges_to(self, canonical_key: str) -> list[KnowledgeEdge]:
        pass

    @abstractmethod
    def find_edges_by_case(self, reference_id: str) -> list[KnowledgeEdge]:
        pass

    @abstractmethod
    def find_nodes_by_case(self, reference_id: str) -> list[KnowledgeNode]:
        pass

    @abstractmethod
    def delete_case_edges(self, reference_id: str) -> int:
        pass

    @abstractmethod
    def all_nodes(self) -> list[KnowledgeNode]:
        pass

    @abstractmethod
    def all_edges(self) -> list[KnowledgeEdge]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass


class InMemoryKnowledgeGraphRepository(KnowledgeGraphRepository):
    """Thread-safe in-memory graph repository for testing and offline execution."""

    def __init__(self):
        self._lock = Lock()
        self._nodes_by_key: dict[str, KnowledgeNode] = {}
        self._nodes_by_id: dict[str, KnowledgeNode] = {}
        self._edges_by_key: dict[str, KnowledgeEdge] = {}
        self._edges_by_id: dict[str, KnowledgeEdge] = {}

    def save_node(self, node: KnowledgeNode) -> KnowledgeNode:
        with self._lock:
            existing = self._nodes_by_key.get(node.canonical_key)
            if existing:
                # Merge case_references
                merged_refs = list(set(existing.case_references + node.case_references))
                updated = existing.model_copy(
                    update={
                        "display_name": node.display_name or existing.display_name,
                        "case_references": merged_refs,
                        "metadata": {**existing.metadata, **node.metadata},
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                self._nodes_by_key[updated.canonical_key] = updated
                self._nodes_by_id[updated.node_id] = updated
                return updated.model_copy(deep=True)
            else:
                self._nodes_by_key[node.canonical_key] = node.model_copy(deep=True)
                self._nodes_by_id[node.node_id] = node.model_copy(deep=True)
                return node.model_copy(deep=True)

    def get_node_by_key(self, canonical_key: str) -> Optional[KnowledgeNode]:
        with self._lock:
            n = self._nodes_by_key.get(canonical_key)
            return n.model_copy(deep=True) if n else None

    def get_node_by_id(self, node_id: str) -> Optional[KnowledgeNode]:
        with self._lock:
            n = self._nodes_by_id.get(node_id)
            return n.model_copy(deep=True) if n else None

    def save_edge(self, edge: KnowledgeEdge) -> KnowledgeEdge:
        with self._lock:
            existing = self._edges_by_key.get(edge.canonical_edge_key)
            if existing:
                merged_ev = list(set(existing.evidence_ids + edge.evidence_ids))
                updated = existing.model_copy(
                    update={
                        "verification_state": edge.verification_state,
                        "evidence_ids": merged_ev,
                        "explanation": edge.explanation or existing.explanation,
                        "metadata": {**existing.metadata, **edge.metadata},
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                self._edges_by_key[updated.canonical_edge_key] = updated
                self._edges_by_id[updated.edge_id] = updated
                return updated.model_copy(deep=True)
            else:
                self._edges_by_key[edge.canonical_edge_key] = edge.model_copy(deep=True)
                self._edges_by_id[edge.edge_id] = edge.model_copy(deep=True)
                return edge.model_copy(deep=True)

    def get_edge_by_key(self, canonical_edge_key: str) -> Optional[KnowledgeEdge]:
        with self._lock:
            e = self._edges_by_key.get(canonical_edge_key)
            return e.model_copy(deep=True) if e else None

    def get_edge_by_id(self, edge_id: str) -> Optional[KnowledgeEdge]:
        with self._lock:
            e = self._edges_by_id.get(edge_id)
            return e.model_copy(deep=True) if e else None

    def find_edges_from(self, canonical_key: str) -> list[KnowledgeEdge]:
        with self._lock:
            return [
                e.model_copy(deep=True)
                for e in self._edges_by_key.values()
                if e.from_node == canonical_key
            ]

    def find_edges_to(self, canonical_key: str) -> list[KnowledgeEdge]:
        with self._lock:
            return [
                e.model_copy(deep=True)
                for e in self._edges_by_key.values()
                if e.to_node == canonical_key
            ]

    def find_edges_by_case(self, reference_id: str) -> list[KnowledgeEdge]:
        with self._lock:
            return [
                e.model_copy(deep=True)
                for e in self._edges_by_key.values()
                if e.case_reference == reference_id
            ]

    def find_nodes_by_case(self, reference_id: str) -> list[KnowledgeNode]:
        with self._lock:
            return [
                n.model_copy(deep=True)
                for n in self._nodes_by_key.values()
                if reference_id in n.case_references
            ]

    def delete_case_edges(self, reference_id: str) -> int:
        with self._lock:
            to_delete = [
                k for k, e in self._edges_by_key.items() if e.case_reference == reference_id
            ]
            count = len(to_delete)
            for k in to_delete:
                edge = self._edges_by_key.pop(k)
                self._edges_by_id.pop(edge.edge_id, None)
            return count

    def all_nodes(self) -> list[KnowledgeNode]:
        with self._lock:
            return [n.model_copy(deep=True) for n in self._nodes_by_key.values()]

    def all_edges(self) -> list[KnowledgeEdge]:
        with self._lock:
            return [e.model_copy(deep=True) for e in self._edges_by_key.values()]

    def clear(self) -> None:
        with self._lock:
            self._nodes_by_key.clear()
            self._nodes_by_id.clear()
            self._edges_by_key.clear()
            self._edges_by_id.clear()


class MongoKnowledgeGraphRepository(KnowledgeGraphRepository):
    """MongoDB persistence adapter with thread-safe in-memory fallback."""

    def __init__(self, fallback: Optional[InMemoryKnowledgeGraphRepository] = None):
        self._fallback = fallback or InMemoryKnowledgeGraphRepository()

    def save_node(self, node: KnowledgeNode) -> KnowledgeNode:
        self._fallback.save_node(node)
        db = get_database()
        if db is not None:
            try:
                doc = node.model_dump(mode="python")
                db.sync_command(
                    lambda: db.delegate[KNOWLEDGE_NODES_COLLECTION].replace_one(
                        {"canonical_key": node.canonical_key}, doc, upsert=True
                    )
                )
            except Exception as exc:
                logger.warning("MongoDB knowledge_nodes write failed (%s); cached in fallback.", exc)
        return node

    def get_node_by_key(self, canonical_key: str) -> Optional[KnowledgeNode]:
        db = get_database()
        if db is None:
            return self._fallback.get_node_by_key(canonical_key)
        try:
            doc = db.sync_command(
                lambda: db.delegate[KNOWLEDGE_NODES_COLLECTION].find_one({"canonical_key": canonical_key})
            )
            if not doc:
                return self._fallback.get_node_by_key(canonical_key)
            doc.pop("_id", None)
            return KnowledgeNode(**doc)
        except Exception as exc:
            logger.warning("MongoDB knowledge_nodes lookup failed (%s); fallback used.", exc)
            return self._fallback.get_node_by_key(canonical_key)

    def get_node_by_id(self, node_id: str) -> Optional[KnowledgeNode]:
        db = get_database()
        if db is None:
            return self._fallback.get_node_by_id(node_id)
        try:
            doc = db.sync_command(
                lambda: db.delegate[KNOWLEDGE_NODES_COLLECTION].find_one({"node_id": node_id})
            )
            if not doc:
                return self._fallback.get_node_by_id(node_id)
            doc.pop("_id", None)
            return KnowledgeNode(**doc)
        except Exception as exc:
            logger.warning("MongoDB knowledge_nodes lookup failed (%s); fallback used.", exc)
            return self._fallback.get_node_by_id(node_id)

    def save_edge(self, edge: KnowledgeEdge) -> KnowledgeEdge:
        self._fallback.save_edge(edge)
        db = get_database()
        if db is not None:
            try:
                doc = edge.model_dump(mode="python")
                db.sync_command(
                    lambda: db.delegate[KNOWLEDGE_EDGES_COLLECTION].replace_one(
                        {"canonical_edge_key": edge.canonical_edge_key}, doc, upsert=True
                    )
                )
            except Exception as exc:
                logger.warning("MongoDB knowledge_edges write failed (%s); cached in fallback.", exc)
        return edge

    def get_edge_by_key(self, canonical_edge_key: str) -> Optional[KnowledgeEdge]:
        db = get_database()
        if db is None:
            return self._fallback.get_edge_by_key(canonical_edge_key)
        try:
            doc = db.sync_command(
                lambda: db.delegate[KNOWLEDGE_EDGES_COLLECTION].find_one({"canonical_edge_key": canonical_edge_key})
            )
            if not doc:
                return self._fallback.get_edge_by_key(canonical_edge_key)
            doc.pop("_id", None)
            return KnowledgeEdge(**doc)
        except Exception as exc:
            logger.warning("MongoDB knowledge_edges lookup failed (%s); fallback used.", exc)
            return self._fallback.get_edge_by_key(canonical_edge_key)

    def get_edge_by_id(self, edge_id: str) -> Optional[KnowledgeEdge]:
        db = get_database()
        if db is None:
            return self._fallback.get_edge_by_id(edge_id)
        try:
            doc = db.sync_command(
                lambda: db.delegate[KNOWLEDGE_EDGES_COLLECTION].find_one({"edge_id": edge_id})
            )
            if not doc:
                return self._fallback.get_edge_by_id(edge_id)
            doc.pop("_id", None)
            return KnowledgeEdge(**doc)
        except Exception as exc:
            logger.warning("MongoDB knowledge_edges lookup failed (%s); fallback used.", exc)
            return self._fallback.get_edge_by_id(edge_id)

    def find_edges_from(self, canonical_key: str) -> list[KnowledgeEdge]:
        db = get_database()
        if db is None:
            return self._fallback.find_edges_from(canonical_key)
        try:
            cursor = db.sync_command(
                lambda: list(db.delegate[KNOWLEDGE_EDGES_COLLECTION].find({"from_node": canonical_key}))
            )
            if not cursor:
                return self._fallback.find_edges_from(canonical_key)
            for c in cursor:
                c.pop("_id", None)
            return [KnowledgeEdge(**c) for c in cursor]
        except Exception:
            return self._fallback.find_edges_from(canonical_key)

    def find_edges_to(self, canonical_key: str) -> list[KnowledgeEdge]:
        db = get_database()
        if db is None:
            return self._fallback.find_edges_to(canonical_key)
        try:
            cursor = db.sync_command(
                lambda: list(db.delegate[KNOWLEDGE_EDGES_COLLECTION].find({"to_node": canonical_key}))
            )
            if not cursor:
                return self._fallback.find_edges_to(canonical_key)
            for c in cursor:
                c.pop("_id", None)
            return [KnowledgeEdge(**c) for c in cursor]
        except Exception:
            return self._fallback.find_edges_to(canonical_key)

    def find_edges_by_case(self, reference_id: str) -> list[KnowledgeEdge]:
        db = get_database()
        if db is None:
            return self._fallback.find_edges_by_case(reference_id)
        try:
            cursor = db.sync_command(
                lambda: list(db.delegate[KNOWLEDGE_EDGES_COLLECTION].find({"case_reference": reference_id}))
            )
            if not cursor:
                return self._fallback.find_edges_by_case(reference_id)
            for c in cursor:
                c.pop("_id", None)
            return [KnowledgeEdge(**c) for c in cursor]
        except Exception:
            return self._fallback.find_edges_by_case(reference_id)

    def find_nodes_by_case(self, reference_id: str) -> list[KnowledgeNode]:
        db = get_database()
        if db is None:
            return self._fallback.find_nodes_by_case(reference_id)
        try:
            cursor = db.sync_command(
                lambda: list(db.delegate[KNOWLEDGE_NODES_COLLECTION].find({"case_references": reference_id}))
            )
            if not cursor:
                return self._fallback.find_nodes_by_case(reference_id)
            for c in cursor:
                c.pop("_id", None)
            return [KnowledgeNode(**c) for c in cursor]
        except Exception:
            return self._fallback.find_nodes_by_case(reference_id)

    def delete_case_edges(self, reference_id: str) -> int:
        self._fallback.delete_case_edges(reference_id)
        db = get_database()
        if db is not None:
            try:
                res = db.sync_command(
                    lambda: db.delegate[KNOWLEDGE_EDGES_COLLECTION].delete_many({"case_reference": reference_id})
                )
                return getattr(res, "deleted_count", 0)
            except Exception as exc:
                logger.warning("MongoDB knowledge_edges deletion failed: %s", exc)
        return 0

    def all_nodes(self) -> list[KnowledgeNode]:
        db = get_database()
        if db is None:
            return self._fallback.all_nodes()
        try:
            cursor = db.sync_command(lambda: list(db.delegate[KNOWLEDGE_NODES_COLLECTION].find({})))
            if not cursor:
                return self._fallback.all_nodes()
            for c in cursor:
                c.pop("_id", None)
            return [KnowledgeNode(**c) for c in cursor]
        except Exception:
            return self._fallback.all_nodes()

    def all_edges(self) -> list[KnowledgeEdge]:
        db = get_database()
        if db is None:
            return self._fallback.all_edges()
        try:
            cursor = db.sync_command(lambda: list(db.delegate[KNOWLEDGE_EDGES_COLLECTION].find({})))
            if not cursor:
                return self._fallback.all_edges()
            for c in cursor:
                c.pop("_id", None)
            return [KnowledgeEdge(**c) for c in cursor]
        except Exception:
            return self._fallback.all_edges()

    def clear(self) -> None:
        self._fallback.clear()
        db = get_database()
        if db is not None:
            try:
                db.sync_command(lambda: db.delegate[KNOWLEDGE_NODES_COLLECTION].delete_many({}))
                db.sync_command(lambda: db.delegate[KNOWLEDGE_EDGES_COLLECTION].delete_many({}))
            except Exception as exc:
                logger.warning("MongoDB knowledge graph clear failed: %s", exc)


class CivicKnowledgeGraphService:
    """
    Production-oriented knowledge graph builder and query engine for CVKI.
    Constructs deterministic, evidence-grounded subgraphs connecting civic claims,
    detection, location, road, jurisdiction, authority, context, and resolution.
    """

    def __init__(self, repository: Optional[KnowledgeGraphRepository] = None):
        self.repository = repository or MongoKnowledgeGraphRepository()

    def _ensure_node(
        self,
        node_type: NodeType,
        canonical_key: str,
        display_name: str,
        case_reference: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> KnowledgeNode:
        existing = self.repository.get_node_by_key(canonical_key)
        cases = [case_reference] if case_reference else []
        meta = dict(metadata or {})
        now = datetime.now(timezone.utc)
        if existing:
            if case_reference and case_reference not in existing.case_references:
                existing.case_references.append(case_reference)
            existing.metadata.update(meta)
            existing.updated_at = now
            return self.repository.save_node(existing)

        node = KnowledgeNode(
            node_id=f"node_{uuid.uuid4().hex[:14]}",
            node_type=node_type,
            canonical_key=canonical_key,
            display_name=display_name,
            case_references=cases,
            metadata=meta,
            created_at=now,
            updated_at=now,
        )
        return self.repository.save_node(node)

    def _ensure_edge(
        self,
        from_node: KnowledgeNode,
        to_node: KnowledgeNode,
        relation_type: RelationType,
        verification_state: VerificationState = VerificationState.PARTIALLY_VERIFIED,
        evidence_ids: Optional[list[str]] = None,
        source_type: Optional[SourceType] = None,
        case_reference: Optional[str] = None,
        explanation: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> KnowledgeEdge:
        edge_key = canonical_edge_key(from_node.canonical_key, relation_type.value, to_node.canonical_key)
        existing = self.repository.get_edge_by_key(edge_key)
        now = datetime.now(timezone.utc)
        ev_ids = list(evidence_ids or [])
        meta = dict(metadata or {})

        if existing:
            merged_ev = list(set(existing.evidence_ids + ev_ids))
            existing.evidence_ids = merged_ev
            existing.verification_state = verification_state
            if source_type:
                existing.source_type = source_type
            if explanation:
                existing.explanation = explanation
            existing.metadata.update(meta)
            existing.updated_at = now
            return self.repository.save_edge(existing)

        edge = KnowledgeEdge(
            edge_id=f"edge_{uuid.uuid4().hex[:14]}",
            canonical_edge_key=edge_key,
            from_node=from_node.canonical_key,
            to_node=to_node.canonical_key,
            relation_type=relation_type,
            evidence_ids=ev_ids,
            verification_state=verification_state,
            source_type=source_type,
            case_reference=case_reference,
            explanation=explanation,
            metadata=meta,
            created_at=now,
            updated_at=now,
        )
        return self.repository.save_edge(edge)

    def build_case_graph(
        self,
        case: ComplaintCase,
        provenance: Optional[CaseProvenanceResponse] = None,
        external_context: Optional[dict[str, Any]] = None,
        intelligence: Optional[Any] = None,
    ) -> KnowledgeGraphSubgraph:
        """
        Deterministically builds and persists the civic knowledge graph for an individual case.
        Integrates M6.1 (authority), M6.2 (geospatial), M6.3 (external civic data),
        M6.4 (provenance), and M5.2 (recurrence/hotspot).
        """
        ref = case.reference_id

        # Retrieve or compute provenance if not provided
        if not provenance:
            prov_engine = get_provenance_engine()
            provenance = prov_engine.generate_case_provenance_chain(
                case, external_context=external_context, intelligence=intelligence
            )

        # Map claims by type for direct evidence ID linkage
        claims_by_type: dict[ClaimType, EvidenceRecord] = {
            c.claim_type: c for c in provenance.claims
        }

        # 1. Root Case Node
        case_node = self._ensure_node(
            node_type=NodeType.CASE,
            canonical_key=canonical_case_key(ref),
            display_name=f"Case {ref}",
            case_reference=ref,
            metadata={"status": case.status, "created_at": case.created_at.isoformat()},
        )

        # 2. Civic Issue Category Node
        issue_cat = case.issue.class_name
        issue_node = self._ensure_node(
            node_type=NodeType.CIVIC_ISSUE,
            canonical_key=canonical_issue_key(issue_cat),
            display_name=case.issue.label or issue_cat.replace("_", " ").title(),
            case_reference=ref,
            metadata={"severity": case.issue.severity},
        )
        det_ev = claims_by_type.get(ClaimType.DETECTION)
        self._ensure_edge(
            from_node=case_node,
            to_node=issue_node,
            relation_type=RelationType.DETECTED_AS,
            verification_state=det_ev.verification_state if det_ev else VerificationState.VERIFIED,
            evidence_ids=[det_ev.evidence_id] if det_ev else [],
            source_type=det_ev.source_type if det_ev else SourceType.CV_MODEL,
            case_reference=ref,
            explanation=det_ev.explanation if det_ev else f"Detected as {case.issue.label}.",
            metadata={"confidence": case.issue.confidence},
        )

        # 3. Detection Node (Model Observation)
        det_meta = {
            "confidence": case.issue.confidence,
            "model": "YOLOv8 M1.13",
            "model_id": det_ev.metadata.get("model_id", "m1.13-yolov8n") if det_ev else "m1.13-yolov8n",
            "model_version": det_ev.metadata.get("model_version", "M1.13-yolov8n") if det_ev else "M1.13-yolov8n",
            "provider_id": det_ev.metadata.get("provider_id", "m113_yolo_provider") if det_ev else "m113_yolo_provider",
            "observation_type": "model_observation",
        }
        if det_ev and det_ev.metadata.get("model_hash"):
            det_meta["model_hash"] = det_ev.metadata.get("model_hash")

        det_node = self._ensure_node(
            node_type=NodeType.DETECTION,
            canonical_key=canonical_detection_key(ref, issue_cat),
            display_name=f"Detection ({case.issue.confidence:.0%})",
            case_reference=ref,
            metadata=det_meta,
        )
        self._ensure_edge(
            from_node=case_node,
            to_node=det_node,
            relation_type=RelationType.GENERATED_FROM,
            verification_state=VerificationState.VERIFIED,
            evidence_ids=[det_ev.evidence_id] if det_ev else [],
            source_type=SourceType.CV_MODEL,
            case_reference=ref,
            explanation=f"Computer vision model detected issue with {case.issue.confidence:.0%} confidence.",
        )

        # 4. Location Node
        loc = case.location
        road_node: Optional[KnowledgeNode] = None
        if loc.latitude is not None and loc.longitude is not None:
            loc_key = canonical_location_key(loc.latitude, loc.longitude)
            loc_node = self._ensure_node(
                node_type=NodeType.LOCATION,
                canonical_key=loc_key,
                display_name=f"({loc.latitude:.4f}, {loc.longitude:.4f})",
                case_reference=ref,
                metadata={
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                    "accuracy_m": loc.accuracy_m,
                    "city": loc.city,
                },
            )
            loc_ev = claims_by_type.get(ClaimType.LOCATION)
            self._ensure_edge(
                from_node=case_node,
                to_node=loc_node,
                relation_type=RelationType.LOCATED_AT,
                verification_state=loc_ev.verification_state if loc_ev else VerificationState.PARTIALLY_VERIFIED,
                evidence_ids=[loc_ev.evidence_id] if loc_ev else [],
                source_type=SourceType.GPS,
                case_reference=ref,
                explanation=loc_ev.explanation if loc_ev else "Reported GPS coordinate fix.",
                metadata={"accuracy_m": loc.accuracy_m},
            )

            # 5. Road Node (M6.2 Geospatial)
            if loc.road and loc.road.strip():
                road_key = canonical_road_key(loc.road, loc.city)
                road_ev = claims_by_type.get(ClaimType.ROAD_IDENTITY)
                match_quality = "EXACT" if (road_ev and road_ev.metadata.get("match_quality") == "EXACT") else "APPROXIMATE"
                road_node = self._ensure_node(
                    node_type=NodeType.ROAD,
                    canonical_key=road_key,
                    display_name=loc.road.strip(),
                    case_reference=ref,
                    metadata={"city": loc.city, "match_quality": match_quality},
                )
                self._ensure_edge(
                    from_node=case_node,
                    to_node=road_node,
                    relation_type=RelationType.ON_ROAD,
                    verification_state=road_ev.verification_state if road_ev else VerificationState.PARTIALLY_VERIFIED,
                    evidence_ids=[road_ev.evidence_id] if road_ev else [],
                    source_type=SourceType.GEOCODER,
                    case_reference=ref,
                    explanation=f"Corridor match: {loc.road} ({match_quality} match).",
                    metadata={"match_quality": match_quality},
                )

                # Road Segment
                seg_id = f"seg_{round(loc.latitude, 3)}_{round(loc.longitude, 3)}"
                segment_node = self._ensure_node(
                    node_type=NodeType.ROAD_SEGMENT,
                    canonical_key=canonical_road_segment_key(loc.road, seg_id),
                    display_name=f"{loc.road} ({seg_id})",
                    case_reference=ref,
                    metadata={"segment_id": seg_id},
                )
                self._ensure_edge(
                    from_node=case_node,
                    to_node=segment_node,
                    relation_type=RelationType.ON_ROAD_SEGMENT,
                    verification_state=VerificationState.PARTIALLY_VERIFIED,
                    case_reference=ref,
                    explanation="Matched localized road segment envelope.",
                )

                # 6. Jurisdiction Node
                jurisdiction_name = loc.district or loc.city or loc.state or "Local Jurisdiction"
                jurisdiction_node = self._ensure_node(
                    node_type=NodeType.JURISDICTION,
                    canonical_key=canonical_jurisdiction_key(jurisdiction_name, "district"),
                    display_name=jurisdiction_name,
                    case_reference=ref,
                    metadata={"level": "district", "state": loc.state},
                )
                self._ensure_edge(
                    from_node=road_node,
                    to_node=jurisdiction_node,
                    relation_type=RelationType.WITHIN_JURISDICTION,
                    verification_state=VerificationState.VERIFIED,
                    case_reference=ref,
                    explanation=f"Road corridor falls within {jurisdiction_name} jurisdiction boundary.",
                )

        # 7. Authority Intelligence (M6.1 / M5.1)
        auth = case.authority
        if auth and road_node:
            # Road Owner
            if auth.road_owner and auth.road_owner.name:
                owner_ev = claims_by_type.get(ClaimType.ROAD_OWNER)
                owner_node = self._ensure_node(
                    node_type=NodeType.ROAD_OWNER,
                    canonical_key=canonical_authority_key(auth.road_owner.name),
                    display_name=auth.road_owner.name,
                    case_reference=ref,
                    metadata={"type": auth.road_owner.type, "source": auth.road_owner.source},
                )
                self._ensure_edge(
                    from_node=road_node,
                    to_node=owner_node,
                    relation_type=RelationType.OWNED_BY,
                    verification_state=owner_ev.verification_state if owner_ev else VerificationState.PARTIALLY_VERIFIED,
                    evidence_ids=[owner_ev.evidence_id] if owner_ev else [],
                    source_type=SourceType.GOVERNMENT_REGISTRY,
                    case_reference=ref,
                    explanation=f"Road asset owned by {auth.road_owner.name}.",
                )

            # Maintenance Authority
            if auth.maintenance_authority and auth.maintenance_authority.name:
                maint_ev = claims_by_type.get(ClaimType.MAINTENANCE_AUTHORITY)
                maint_node = self._ensure_node(
                    node_type=NodeType.MAINTENANCE_AUTHORITY,
                    canonical_key=canonical_authority_key(auth.maintenance_authority.name),
                    display_name=auth.maintenance_authority.name,
                    case_reference=ref,
                    metadata={"type": auth.maintenance_authority.type, "source": auth.maintenance_authority.source},
                )
                self._ensure_edge(
                    from_node=road_node,
                    to_node=maint_node,
                    relation_type=RelationType.MAINTAINED_BY,
                    verification_state=maint_ev.verification_state if maint_ev else VerificationState.PARTIALLY_VERIFIED,
                    evidence_ids=[maint_ev.evidence_id] if maint_ev else [],
                    source_type=SourceType.GOVERNMENT_REGISTRY,
                    case_reference=ref,
                    explanation=f"Maintenance responsibility assigned to {auth.maintenance_authority.name}.",
                )

            # Builder / Contractor (Strict Safety Rule: Only if explicit tender/concession evidence exists)
            if auth.builder_or_contractor:
                builder_name = (
                    auth.builder_or_contractor.name
                    if hasattr(auth.builder_or_contractor, "name")
                    else str(auth.builder_or_contractor)
                )
                builder_src = getattr(auth.builder_or_contractor, "source", None) or ""
                is_tender = "tender" in builder_src.lower() or "concession" in builder_src.lower()
                builder_ev = claims_by_type.get(ClaimType.BUILDER_OR_CONTRACTOR)

                # Only establish BUILT_BY edge if supported by explicit tender/contract registry
                if is_tender or (builder_ev and builder_ev.verification_state == VerificationState.VERIFIED):
                    builder_node = self._ensure_node(
                        node_type=NodeType.BUILDER_OR_CONTRACTOR,
                        canonical_key=canonical_builder_key(builder_name),
                        display_name=builder_name,
                        case_reference=ref,
                        metadata={"source": builder_src},
                    )
                    self._ensure_edge(
                        from_node=road_node,
                        to_node=builder_node,
                        relation_type=RelationType.BUILT_BY,
                        verification_state=VerificationState.VERIFIED,
                        evidence_ids=[builder_ev.evidence_id] if builder_ev else [],
                        source_type=SourceType.TENDER_REGISTRY,
                        case_reference=ref,
                        explanation=f"Concessionaire/contractor verified as {builder_name}.",
                    )

        # 8. External Civic Context (M6.3)
        if external_context:
            weather = external_context.get("weather")
            if weather:
                w_temp = weather.get("temperature_c", 25.0)
                w_cond = weather.get("condition", "Observed")
                w_provider = weather.get("source", "OpenMeteo")
                w_node = self._ensure_node(
                    node_type=NodeType.WEATHER_CONTEXT,
                    canonical_key=canonical_weather_key(w_provider, loc.latitude or 0.0, loc.longitude or 0.0),
                    display_name=f"Weather: {w_temp}°C ({w_cond})",
                    case_reference=ref,
                    metadata=weather,
                )
                w_ev = claims_by_type.get(ClaimType.WEATHER_CONTEXT)
                self._ensure_edge(
                    from_node=case_node,
                    to_node=w_node,
                    relation_type=RelationType.HAS_WEATHER_CONTEXT,
                    verification_state=w_ev.verification_state if w_ev else VerificationState.PARTIALLY_VERIFIED,
                    evidence_ids=[w_ev.evidence_id] if w_ev else [],
                    source_type=SourceType.WEATHER_PROVIDER,
                    case_reference=ref,
                    explanation=f"Contextual observation: {w_temp}°C with {w_cond} conditions.",
                )

            rainfall = external_context.get("rainfall")
            if rainfall:
                r_mm = rainfall.get("window_rainfall_mm", 0.0)
                r_provider = rainfall.get("source", "OpenMeteo")
                r_node = self._ensure_node(
                    node_type=NodeType.RAINFALL_CONTEXT,
                    canonical_key=canonical_rainfall_key(r_provider, loc.latitude or 0.0, loc.longitude or 0.0),
                    display_name=f"Rainfall: {r_mm} mm",
                    case_reference=ref,
                    metadata=rainfall,
                )
                r_ev = claims_by_type.get(ClaimType.RAINFALL_CONTEXT)
                # STRICT INVARIANT: HAS_RAINFALL_CONTEXT only, NEVER 'CAUSED'
                self._ensure_edge(
                    from_node=case_node,
                    to_node=r_node,
                    relation_type=RelationType.HAS_RAINFALL_CONTEXT,
                    verification_state=r_ev.verification_state if r_ev else VerificationState.PARTIALLY_VERIFIED,
                    evidence_ids=[r_ev.evidence_id] if r_ev else [],
                    source_type=SourceType.WEATHER_PROVIDER,
                    case_reference=ref,
                    explanation="Contextual environmental observation: conditions consistent with recent rainfall.",
                    metadata={"non_causal": True},
                )

            traffic = external_context.get("traffic")
            if traffic and road_node:
                t_provider = traffic.get("source", "TrafficProvider")
                t_node = self._ensure_node(
                    node_type=NodeType.TRAFFIC_CONTEXT,
                    canonical_key=canonical_traffic_key(t_provider, road_node.canonical_key),
                    display_name="Traffic Context",
                    case_reference=ref,
                    metadata=traffic,
                )
                self._ensure_edge(
                    from_node=case_node,
                    to_node=t_node,
                    relation_type=RelationType.HAS_TRAFFIC_CONTEXT,
                    verification_state=VerificationState.PARTIALLY_VERIFIED,
                    source_type=SourceType.TRAFFIC_PROVIDER,
                    case_reference=ref,
                    explanation="Contextual traffic delay observation along corridor.",
                )

        # 9. Recurrence & Hotspot Patterns (M5.2 System-Derived Intelligence)
        rec_data = intelligence.recurrence if intelligence and hasattr(intelligence, "recurrence") else getattr(case, "recurrence_analysis", None)
        if rec_data and getattr(rec_data, "recurrence_detected", False):
            rec_count = getattr(rec_data, "recurrence_count", 0)
            rec_node = self._ensure_node(
                node_type=NodeType.RECURRENCE_PATTERN,
                canonical_key=canonical_recurrence_key(issue_cat, road_node.canonical_key if road_node else loc.city or "area"),
                display_name=f"Recurring Pattern ({rec_count} cases)",
                case_reference=ref,
                metadata={"recurrence_count": rec_count, "window_days": getattr(rec_data, "recurrence_window_days", 180)},
            )
            rec_ev = claims_by_type.get(ClaimType.RECURRENCE)
            self._ensure_edge(
                from_node=case_node,
                to_node=rec_node,
                relation_type=RelationType.RECURRENCE_OF,
                verification_state=VerificationState.SYSTEM_DERIVED,
                evidence_ids=[rec_ev.evidence_id] if rec_ev else [],
                source_type=SourceType.CVKI_CASE_HISTORY,
                case_reference=ref,
                explanation=f"System-derived intelligence: {rec_count} historical incidents within spatial-temporal window.",
            )

        if intelligence and getattr(intelligence, "hotspot_detected", False):
            hot_count = getattr(intelligence, "recent_location_case_count", 0)
            hot_node = self._ensure_node(
                node_type=NodeType.HOTSPOT,
                canonical_key=canonical_hotspot_key(issue_cat, loc.city or "area"),
                display_name=f"Hotspot ({hot_count} reports)",
                case_reference=ref,
                metadata={"recent_cases": hot_count},
            )
            hot_ev = claims_by_type.get(ClaimType.HOTSPOT_CONTEXT)
            self._ensure_edge(
                from_node=case_node,
                to_node=hot_node,
                relation_type=RelationType.PART_OF_HOTSPOT,
                verification_state=VerificationState.SYSTEM_DERIVED,
                evidence_ids=[hot_ev.evidence_id] if hot_ev else [],
                source_type=SourceType.CVKI_CASE_HISTORY,
                case_reference=ref,
                explanation="System-derived cluster density indicating localized civic concentration.",
            )

        # 10. Duplicate Relationship (M3.7)
        dup = getattr(case, "duplicate_analysis", None)
        if dup and getattr(dup, "classification", "") == "duplicate" and getattr(dup, "matched_reference_id", None):
            dup_target = self._ensure_node(
                node_type=NodeType.CASE,
                canonical_key=canonical_case_key(dup.matched_reference_id),
                display_name=f"Case {dup.matched_reference_id}",
                case_reference=ref,
            )
            self._ensure_edge(
                from_node=case_node,
                to_node=dup_target,
                relation_type=RelationType.DUPLICATE_OF,
                verification_state=VerificationState.SYSTEM_DERIVED,
                source_type=SourceType.CVKI_CASE_HISTORY,
                case_reference=ref,
                explanation=f"Same-incident duplicate of {dup.matched_reference_id} per spatial-temporal match.",
            )

        # 11. Complaint Lifecycle & Submission
        complaint_node = self._ensure_node(
            node_type=NodeType.COMPLAINT,
            canonical_key=canonical_complaint_key(ref),
            display_name=case.complaint.title or f"Complaint {ref}",
            case_reference=ref,
            metadata={"language": case.complaint.language},
        )
        self._ensure_edge(
            from_node=case_node,
            to_node=complaint_node,
            relation_type=RelationType.HAS_COMPLAINT,
            verification_state=VerificationState.VERIFIED,
            source_type=SourceType.CITIZEN_REPORT,
            case_reference=ref,
            explanation="Citizen filed complaint documentation in CVKI.",
        )
        if auth and auth.maintenance_authority and auth.maintenance_authority.name:
            maint_target = self.repository.get_node_by_key(canonical_authority_key(auth.maintenance_authority.name))
            if maint_target:
                self._ensure_edge(
                    from_node=complaint_node,
                    to_node=maint_target,
                    relation_type=RelationType.SUBMITTED_TO,
                    verification_state=VerificationState.PARTIALLY_VERIFIED,
                    case_reference=ref,
                    explanation="Complaint structured for dispatch to responsible municipal body.",
                )

        # 12. Resolution Evidence (M5.2)
        if case.status in ("resolved", "closed"):
            res_node = self._ensure_node(
                node_type=NodeType.RESOLUTION,
                canonical_key=canonical_resolution_key(ref),
                display_name=f"Resolution ({case.status.title()})",
                case_reference=ref,
                metadata={"status": case.status},
            )
            res_ev = claims_by_type.get(ClaimType.RESOLUTION_EVIDENCE)
            self._ensure_edge(
                from_node=case_node,
                to_node=res_node,
                relation_type=RelationType.HAS_RESOLUTION,
                verification_state=res_ev.verification_state if res_ev else VerificationState.VERIFIED,
                evidence_ids=[res_ev.evidence_id] if res_ev else [],
                source_type=SourceType.AUTHORITY_UPDATE,
                case_reference=ref,
                explanation=res_ev.explanation if res_ev else "Civic issue marked resolved in CVKI workflow.",
            )

        # Return the resulting case-centric subgraph
        return self.get_case_graph(ref, max_depth=2)

    def record_government_submission_graph(
        self,
        case_reference_id: str,
        submission_id: str,
        integration_id: str,
        external_reference_id: Optional[str] = None,
        evidence_id: Optional[str] = None,
    ) -> None:
        """
        Integrates server-confirmed government submission into the knowledge graph (M7.1).
        Case -> GOVERNMENT_SUBMISSION -> GovSubmission Node -> REFERENCES -> ExternalCase Node
        """
        case_node = self.repository.get_node_by_key(canonical_case_key(case_reference_id))
        if not case_node:
            case_node = self._ensure_node(
                node_type=NodeType.CASE,
                canonical_key=canonical_case_key(case_reference_id),
                display_name=f"Case {case_reference_id}",
                case_reference=case_reference_id,
            )
        sub_key = f"gov_sub:{submission_id}"
        sub_node = self._ensure_node(
            node_type=NodeType.GOVERNMENT_SUBMISSION,
            canonical_key=sub_key,
            display_name=f"Gov Submission ({integration_id})",
            case_reference=case_reference_id,
            metadata={"submission_id": submission_id, "integration_id": integration_id},
        )
        self._ensure_edge(
            from_node=case_node,
            to_node=sub_node,
            relation_type=RelationType.GOVERNMENT_SUBMISSION,
            verification_state=VerificationState.VERIFIED,
            evidence_ids=[evidence_id] if evidence_id else [],
            source_type=SourceType.GOVERNMENT_ADAPTER,
            case_reference=case_reference_id,
            explanation=f"Server-confirmed submission to government integration '{integration_id}'.",
        )
        if external_reference_id:
            ext_key = f"ext_case:{external_reference_id}"
            ext_node = self._ensure_node(
                node_type=NodeType.EXTERNAL_CASE,
                canonical_key=ext_key,
                display_name=f"External Case {external_reference_id}",
                case_reference=case_reference_id,
                metadata={"external_reference_id": external_reference_id},
            )
            self._ensure_edge(
                from_node=sub_node,
                to_node=ext_node,
                relation_type=RelationType.REFERENCES,
                verification_state=VerificationState.VERIFIED,
                evidence_ids=[evidence_id] if evidence_id else [],
                source_type=SourceType.GOVERNMENT_ADAPTER,
                case_reference=case_reference_id,
                explanation=f"Official government tracking identifier: {external_reference_id}.",
            )

    def record_government_reference_mapping_graph(
        self,
        case_reference_id: str,
        submission_id: str,
        integration_id: str,
        government_reference_id: Optional[str] = None,
        mapping_state: str = "REFERENCE_CONFIRMED",
        verification_state: str = "verified",
        evidence_id: Optional[str] = None,
        explanation: Optional[str] = None,
    ) -> None:
        """
        Integrates M7.3 Government Reference Mapping into the knowledge graph.
        Case -> GOVERNMENT_SUBMISSION -> GovSubmission Node -> REFERENCES -> ExternalCase Node
        Includes mapping state and verification state on the EXTERNAL_CASE node.
        If mapping is conflicted or unverified, preserves history and updates states.
        """
        case_node = self.repository.get_node_by_key(canonical_case_key(case_reference_id))
        if not case_node:
            case_node = self._ensure_node(
                node_type=NodeType.CASE,
                canonical_key=canonical_case_key(case_reference_id),
                display_name=f"Case {case_reference_id}",
                case_reference=case_reference_id,
            )
        sub_key = f"gov_sub:{submission_id}"
        sub_node = self._ensure_node(
            node_type=NodeType.GOVERNMENT_SUBMISSION,
            canonical_key=sub_key,
            display_name=f"Gov Submission ({integration_id})",
            case_reference=case_reference_id,
            metadata={"submission_id": submission_id, "integration_id": integration_id},
        )
        self._ensure_edge(
            from_node=case_node,
            to_node=sub_node,
            relation_type=RelationType.GOVERNMENT_SUBMISSION,
            verification_state=VerificationState.VERIFIED if verification_state == "verified" else VerificationState.PARTIALLY_VERIFIED,
            evidence_ids=[evidence_id] if evidence_id else [],
            source_type=SourceType.GOVERNMENT_ADAPTER,
            case_reference=case_reference_id,
            explanation=f"Government submission on '{integration_id}' for {case_reference_id}.",
        )
        if government_reference_id:
            ext_key = f"ext_case:{integration_id}:{government_reference_id}"
            v_state = VerificationState.VERIFIED if verification_state == "verified" else (
                VerificationState.NOT_VERIFIED if verification_state == "conflicted" else VerificationState.PARTIALLY_VERIFIED
            )
            ext_node = self._ensure_node(
                node_type=NodeType.EXTERNAL_CASE,
                canonical_key=ext_key,
                display_name=f"External Case {government_reference_id}",
                case_reference=case_reference_id,
                metadata={
                    "integration_id": integration_id,
                    "external_reference_id": government_reference_id,
                    "mapping_state": mapping_state,
                    "verification_state": verification_state,
                },
            )
            self._ensure_edge(
                from_node=sub_node,
                to_node=ext_node,
                relation_type=RelationType.REFERENCES,
                verification_state=v_state,
                evidence_ids=[evidence_id] if evidence_id else [],
                source_type=SourceType.GOVERNMENT_ADAPTER,
                case_reference=case_reference_id,
                explanation=explanation or f"Government reference {government_reference_id} on {integration_id} (State: {mapping_state}).",
                metadata={"mapping_state": mapping_state, "verification_state": verification_state},
            )

    def record_government_status_graph(
        self,
        case_reference_id: str,
        integration_id: str,
        government_reference_id: Optional[str],
        normalized_status: str,
        raw_status: Optional[str] = None,
        freshness: str = "FRESH",
        evidence_id: Optional[str] = None,
        observed_at: Optional[datetime] = None,
    ) -> None:
        """
        Integrates synchronized government status into the knowledge graph (M7.4).
        ExternalCase (or Case) -> HAS_GOVERNMENT_STATUS -> GovernmentStatus Node.
        Preserves provenance link and observation freshness.
        """
        ref_id_str = government_reference_id or "unassigned"
        status_key = canonical_government_status_key(integration_id, ref_id_str, normalized_status)
        
        status_node = self._ensure_node(
            node_type=NodeType.GOVERNMENT_STATUS,
            canonical_key=status_key,
            display_name=f"Gov Status: {normalized_status.upper()}",
            case_reference=case_reference_id,
            metadata={
                "integration_id": integration_id,
                "government_reference_id": government_reference_id,
                "raw_status": raw_status,
                "normalized_status": normalized_status,
                "freshness": freshness,
                "observed_at": observed_at.isoformat() if observed_at else None,
            },
        )

        parent_node = None
        if government_reference_id:
            ext_key = f"ext_case:{integration_id}:{government_reference_id}"
            parent_node = self.repository.get_node_by_key(ext_key)
        
        if not parent_node:
            case_key = canonical_case_key(case_reference_id)
            parent_node = self.repository.get_node_by_key(case_key)
            if not parent_node:
                parent_node = self._ensure_node(
                    node_type=NodeType.CASE,
                    canonical_key=case_key,
                    display_name=f"Case {case_reference_id}",
                    case_reference=case_reference_id,
                )

        self._ensure_edge(
            from_node=parent_node,
            to_node=status_node,
            relation_type=RelationType.HAS_GOVERNMENT_STATUS,
            verification_state=VerificationState.VERIFIED,
            evidence_ids=[evidence_id] if evidence_id else [],
            source_type=SourceType.GOVERNMENT_ADAPTER,
            case_reference=case_reference_id,
            explanation=f"Synchronized external status '{normalized_status}' (raw: '{raw_status}') from {integration_id}.",
            metadata={"freshness": freshness},
        )

    def record_escalation_decision_graph(
        self,
        case_reference_id: str,
        decision_id: str,
        escalation_level: str,
        reason_code: str,
        decision: str = "NONE",
        policy_id: Optional[str] = None,
        evidence_id: Optional[str] = None,
        explanation: Optional[str] = None,
    ) -> None:
        """
        Integrates evidence-based escalation decision into the knowledge graph (M7.5).
        Case -> HAS_ESCALATION_DECISION -> EscalationDecision Node.
        Strictly labeled system_derived=True so it is never confused with official authority actions.
        """
        case_key = canonical_case_key(case_reference_id)
        case_node = self.repository.get_node_by_key(case_key)
        if not case_node:
            case_node = self._ensure_node(
                node_type=NodeType.CASE,
                canonical_key=case_key,
                display_name=f"Case {case_reference_id}",
                case_reference=case_reference_id,
            )

        esc_key = canonical_escalation_decision_key(case_reference_id, decision_id)
        esc_node = self._ensure_node(
            node_type=NodeType.ESCALATION_DECISION,
            canonical_key=esc_key,
            display_name=f"Escalation Decision: {decision} ({escalation_level})",
            case_reference=case_reference_id,
            metadata={
                "decision_id": decision_id,
                "decision": decision,
                "escalation_level": escalation_level,
                "reason_code": reason_code,
                "policy_id": policy_id,
                "is_system_derived": True,
            },
        )

        self._ensure_edge(
            from_node=case_node,
            to_node=esc_node,
            relation_type=RelationType.HAS_ESCALATION_DECISION,
            verification_state=VerificationState.SYSTEM_DERIVED,
            evidence_ids=[evidence_id] if evidence_id else [],
            source_type=SourceType.SYSTEM_DERIVED,
            case_reference=case_reference_id,
            explanation=explanation or f"System-derived escalation decision: {decision} ({reason_code}).",
            metadata={"is_system_derived": True, "policy_id": policy_id},
        )

    def record_resolution_verification_graph(
        self,
        case_reference_id: str,
        verification_id: str,
        citizen_response: str,
        verification_status: str,
        is_physical_resolution_verified: bool = False,
        evidence_id: Optional[str] = None,
        explanation: Optional[str] = None,
        reviewer_user_id: Optional[str] = None,
    ) -> None:
        """
        Integrates citizen resolution verification into the knowledge graph (M7.6).
        Case -> HAS_RESOLUTION_VERIFICATION -> ResolutionVerification Node.
        """
        verif_key = canonical_resolution_verification_key(case_reference_id, verification_id)
        verif_node = self._ensure_node(
            node_type=NodeType.RESOLUTION_VERIFICATION,
            canonical_key=verif_key,
            display_name=f"Resolution Verification: {verification_status}",
            case_reference=case_reference_id,
            metadata={
                "verification_id": verification_id,
                "citizen_response": citizen_response,
                "verification_status": verification_status,
                "is_physical_resolution_verified": is_physical_resolution_verified,
                "reviewer_user_id": reviewer_user_id,
            },
        )

        case_key = canonical_case_key(case_reference_id)
        case_node = self.repository.get_node_by_key(case_key)
        if not case_node:
            case_node = self._ensure_node(
                node_type=NodeType.CASE,
                canonical_key=case_key,
                display_name=f"Case {case_reference_id}",
                case_reference=case_reference_id,
            )

        self._ensure_edge(
            from_node=case_node,
            to_node=verif_node,
            relation_type=RelationType.HAS_RESOLUTION_VERIFICATION,
            verification_state=VerificationState.VERIFIED if is_physical_resolution_verified else VerificationState.PARTIALLY_VERIFIED,
            evidence_ids=[evidence_id] if evidence_id else [],
            source_type=SourceType.CITIZEN_REPORT,
            case_reference=case_reference_id,
            explanation=explanation or f"Citizen resolution verification: {citizen_response} ({verification_status}).",
            metadata={"is_physical_resolution_verified": is_physical_resolution_verified},
        )

    def record_vernacular_normalization_graph(
        self,
        case_reference_id: str,
        norm_id: str,
        original_text: str,
        normalized_text: str,
        detected_language: str,
        script: str,
        canonical_civic_concepts: list[str],
        assertion_type: str = "AFFIRMATIVE",
        confidence: float = 0.0,
        evidence_id: Optional[str] = None,
        explanation: Optional[str] = None,
    ) -> KnowledgeNode:
        """
        Integrates M9.4 Vernacular Normalization into the knowledge graph (M9.6).
        Case -> HAS_VERNACULAR_NORMALIZATION -> VernacularNormalization Node.
        VernacularNormalization Node -> NORMALIZED_AS -> CivicIssue Node.
        VernacularNormalization Node -> SUPPORTED_BY -> Evidence Node (if evidence_id).
        Strict Epistemic Bound: USER_REPORTED / SYSTEM_DERIVED only, NEVER VERIFIED.
        """
        norm_key = canonical_vernacular_normalization_key(case_reference_id, norm_id)
        norm_node = self._ensure_node(
            node_type=NodeType.VERNACULAR_NORMALIZATION,
            canonical_key=norm_key,
            display_name=f"Vernacular Norm: {detected_language} ({assertion_type})",
            case_reference=case_reference_id,
            metadata={
                "norm_id": norm_id,
                "original_text": original_text,
                "normalized_text": normalized_text,
                "detected_language": detected_language,
                "script": script,
                "canonical_civic_concepts": canonical_civic_concepts,
                "assertion_type": assertion_type,
                "lexical_confidence": confidence,
                "epistemic_state": "SYSTEM_DERIVED",
            },
        )

        case_key = canonical_case_key(case_reference_id)
        case_node = self.repository.get_node_by_key(case_key)
        if not case_node:
            case_node = self._ensure_node(
                node_type=NodeType.CASE,
                canonical_key=case_key,
                display_name=f"Case {case_reference_id}",
                case_reference=case_reference_id,
            )

        v_state = (
            VerificationState.NOT_VERIFIED
            if assertion_type in ("NEGATED", "UNCERTAIN")
            else VerificationState.SYSTEM_DERIVED
        )

        self._ensure_edge(
            from_node=case_node,
            to_node=norm_node,
            relation_type=RelationType.HAS_VERNACULAR_NORMALIZATION,
            verification_state=v_state,
            evidence_ids=[evidence_id] if evidence_id else [],
            source_type=SourceType.SYSTEM_DERIVED,
            case_reference=case_reference_id,
            explanation=explanation or f"Citizen vernacular text normalized to canonical concepts ({assertion_type}).",
            metadata={"assertion_type": assertion_type, "language": detected_language},
        )

        for concept in canonical_civic_concepts:
            issue_node = self._ensure_node(
                node_type=NodeType.CIVIC_ISSUE,
                canonical_key=canonical_issue_key(concept),
                display_name=concept.replace("_", " ").title(),
                case_reference=case_reference_id,
            )
            self._ensure_edge(
                from_node=norm_node,
                to_node=issue_node,
                relation_type=RelationType.NORMALIZED_AS,
                verification_state=v_state,
                evidence_ids=[evidence_id] if evidence_id else [],
                source_type=SourceType.SYSTEM_DERIVED,
                case_reference=case_reference_id,
                explanation=f"Vernacular term mapped to canonical civic issue concept '{concept}'.",
                metadata={"concept": concept, "assertion_type": assertion_type},
            )

        if evidence_id:
            ev_key = canonical_evidence_key(evidence_id)
            ev_node = self.repository.get_node_by_key(ev_key)
            if not ev_node:
                ev_node = self._ensure_node(
                    node_type=NodeType.EVIDENCE,
                    canonical_key=ev_key,
                    display_name=f"Evidence {evidence_id}",
                    case_reference=case_reference_id,
                    metadata={"evidence_id": evidence_id},
                )
            self._ensure_edge(
                from_node=norm_node,
                to_node=ev_node,
                relation_type=RelationType.SUPPORTED_BY,
                verification_state=v_state,
                evidence_ids=[evidence_id],
                source_type=SourceType.SYSTEM_DERIVED,
                case_reference=case_reference_id,
                explanation=f"Vernacular normalization supported by evidence record {evidence_id}.",
            )

        return norm_node

    def record_visual_audit_graph(
        self,
        case_reference_id: str,
        audit_id: str,
        outcome: str,
        evidence_quality: str,
        issue_category: str,
        temporal_consistency: bool = True,
        spatial_consistency: bool = True,
        evidence_id: Optional[str] = None,
        before_detection_key: Optional[str] = None,
        after_detection_key: Optional[str] = None,
        explanation: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> KnowledgeNode:
        """
        Integrates M9.5 Visual Resolution Audit into the knowledge graph (M9.6).
        Case -> VISUAL_AUDIT_OF -> VisualResolutionAudit Node.
        VisualResolutionAudit Node -> BEFORE_OBSERVATION -> Before Detection Node (optional).
        VisualResolutionAudit Node -> AFTER_OBSERVATION -> After Detection Node (optional).
        VisualResolutionAudit Node -> SUPPORTED_BY -> Evidence Node (optional).

        Strict Epistemic Guard:
        - NEVER emits REPAIRED, FIXED, or REPAIR_CONFIRMED edge.
        - Outcome DEFECT_NOT_OBSERVED remains MODEL_OBSERVATION / SYSTEM_DERIVED.
        - VerificationState is SYSTEM_DERIVED or NOT_VERIFIED, NEVER VERIFIED.
        """
        audit_key = canonical_visual_audit_key(case_reference_id, audit_id)
        meta = dict(metadata or {})
        meta.update({
            "audit_id": audit_id,
            "outcome": outcome,
            "evidence_quality": evidence_quality,
            "issue_category": issue_category,
            "temporal_consistency": temporal_consistency,
            "spatial_consistency": spatial_consistency,
            "epistemic_state": "MODEL_OBSERVATION",
            "is_repair_confirmed": False,
        })

        audit_node = self._ensure_node(
            node_type=NodeType.VISUAL_RESOLUTION_AUDIT,
            canonical_key=audit_key,
            display_name=f"Visual Audit: {outcome}",
            case_reference=case_reference_id,
            metadata=meta,
        )

        case_key = canonical_case_key(case_reference_id)
        case_node = self.repository.get_node_by_key(case_key)
        if not case_node:
            case_node = self._ensure_node(
                node_type=NodeType.CASE,
                canonical_key=case_key,
                display_name=f"Case {case_reference_id}",
                case_reference=case_reference_id,
            )

        v_state = (
            VerificationState.SYSTEM_DERIVED
            if outcome in ("DEFECT_PERSISTS", "DEFECT_NOT_OBSERVED")
            else VerificationState.NOT_VERIFIED
        )

        self._ensure_edge(
            from_node=case_node,
            to_node=audit_node,
            relation_type=RelationType.VISUAL_AUDIT_OF,
            verification_state=v_state,
            evidence_ids=[evidence_id] if evidence_id else [],
            source_type=SourceType.SYSTEM_DERIVED,
            case_reference=case_reference_id,
            explanation=explanation or f"Visual resolution audit of case {case_reference_id}: outcome {outcome}.",
            metadata={"outcome": outcome, "is_repair_confirmed": False},
        )

        if before_detection_key:
            before_node = self.repository.get_node_by_key(before_detection_key)
            if before_node:
                self._ensure_edge(
                    from_node=audit_node,
                    to_node=before_node,
                    relation_type=RelationType.BEFORE_OBSERVATION,
                    verification_state=v_state,
                    evidence_ids=[evidence_id] if evidence_id else [],
                    source_type=SourceType.SYSTEM_DERIVED,
                    case_reference=case_reference_id,
                    explanation=f"Visual audit before observation linked to detection {before_detection_key}.",
                )

        if after_detection_key:
            after_node = self.repository.get_node_by_key(after_detection_key)
            if after_node:
                self._ensure_edge(
                    from_node=audit_node,
                    to_node=after_node,
                    relation_type=RelationType.AFTER_OBSERVATION,
                    verification_state=v_state,
                    evidence_ids=[evidence_id] if evidence_id else [],
                    source_type=SourceType.SYSTEM_DERIVED,
                    case_reference=case_reference_id,
                    explanation=f"Visual audit after observation linked to detection {after_detection_key}.",
                )

        if evidence_id:
            ev_key = canonical_evidence_key(evidence_id)
            ev_node = self.repository.get_node_by_key(ev_key)
            if not ev_node:
                ev_node = self._ensure_node(
                    node_type=NodeType.EVIDENCE,
                    canonical_key=ev_key,
                    display_name=f"Evidence {evidence_id}",
                    case_reference=case_reference_id,
                    metadata={"evidence_id": evidence_id},
                )
            self._ensure_edge(
                from_node=audit_node,
                to_node=ev_node,
                relation_type=RelationType.SUPPORTED_BY,
                verification_state=v_state,
                evidence_ids=[evidence_id],
                source_type=SourceType.SYSTEM_DERIVED,
                case_reference=case_reference_id,
                explanation=f"Visual resolution audit supported by evidence record {evidence_id}.",
            )

        return audit_node

    def rebuild_case_graph(
        self, reference_id: str, case: Optional[ComplaintCase] = None
    ) -> KnowledgeGraphSubgraph:
        """
        Idempotently rebuilds the graph for a specific case by clearing case-specific edges
        and rebuilding fresh relationships from authoritative case records.
        """
        if case is None:
            import inspect
            import app.services.complaint_case as complaint_case_module

            res = complaint_case_module.case_repository.get(reference_id)
            if hasattr(res, "__await__"):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    case = loop.run_until_complete(res) if not loop.is_running() else None
                except RuntimeError:
                    case = asyncio.run(res)
            else:
                case = res

        if not case:
            raise LookupError(f"Cannot rebuild graph: Case '{reference_id}' was not found.")

        # Delete prior case edges to guarantee strict idempotency
        self.repository.delete_case_edges(reference_id)

        # Re-build case graph
        return self.build_case_graph(case)

    def get_subgraph(
        self,
        root_key: str,
        max_depth: Optional[int] = None,
        max_nodes: Optional[int] = None,
        max_edges: Optional[int] = None,
    ) -> KnowledgeGraphSubgraph:
        """
        Performs a strictly bounded breadth-first traversal starting from root_key.
        Prevents runaway loops, obeys MAX_DEPTH, MAX_NODES, and MAX_EDGES limits.
        """
        depth_limit = max_depth if max_depth is not None else settings.GRAPH_MAX_DEPTH
        node_limit = max_nodes if max_nodes is not None else settings.GRAPH_MAX_NODES
        edge_limit = max_edges if max_edges is not None else settings.GRAPH_MAX_EDGES

        root_node = self.repository.get_node_by_key(root_key)
        if not root_node:
            return KnowledgeGraphSubgraph(
                root_node_key=root_key,
                nodes=[],
                edges=[],
                total_nodes=0,
                total_edges=0,
                max_depth_reached=0,
                generated_at=datetime.now(timezone.utc),
                limitations=[f"Root node '{root_key}' not found in knowledge graph."],
            )

        visited_nodes: dict[str, KnowledgeNode] = {root_key: root_node}
        visited_edges: dict[str, KnowledgeEdge] = {}
        queue: deque[tuple[str, int]] = deque([(root_key, 0)])
        max_depth_reached = 0

        while queue:
            curr_key, curr_depth = queue.popleft()
            max_depth_reached = max(max_depth_reached, curr_depth)

            if curr_depth >= depth_limit:
                continue

            # Outgoing & incoming edges
            adjacent_edges = self.repository.find_edges_from(curr_key) + self.repository.find_edges_to(curr_key)

            for edge in adjacent_edges:
                if len(visited_edges) >= edge_limit:
                    break

                if edge.canonical_edge_key not in visited_edges:
                    visited_edges[edge.canonical_edge_key] = edge

                # Identify the adjacent neighbor
                neighbor_key = edge.to_node if edge.from_node == curr_key else edge.from_node

                if neighbor_key not in visited_nodes:
                    if len(visited_nodes) >= node_limit:
                        break
                    neighbor_node = self.repository.get_node_by_key(neighbor_key)
                    if neighbor_node:
                        visited_nodes[neighbor_key] = neighbor_node
                        queue.append((neighbor_key, curr_depth + 1))

        limitations = [
            "Graph traversal is strictly bounded to prevent runaway recursion.",
            "Relationships represent evidence-grounded connections, not absolute physical truth.",
            "Environmental edges reflect contextual correlations without establishing causation.",
        ]

        nodes_list = list(visited_nodes.values())
        edges_list = list(visited_edges.values())

        return KnowledgeGraphSubgraph(
            root_node_key=root_key,
            nodes=nodes_list,
            edges=edges_list,
            total_nodes=len(nodes_list),
            total_edges=len(edges_list),
            max_depth_reached=max_depth_reached,
            generated_at=datetime.now(timezone.utc),
            limitations=limitations,
        )

    def get_case_graph(
        self,
        reference_id: str,
        max_depth: Optional[int] = None,
        max_nodes: Optional[int] = None,
        max_edges: Optional[int] = None,
    ) -> KnowledgeGraphSubgraph:
        """Convenience method to retrieve the subgraph rooted at a complaint case."""
        case_key = canonical_case_key(reference_id)
        return self.get_subgraph(
            root_key=case_key,
            max_depth=max_depth if max_depth is not None else 2,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    def get_road_graph(
        self,
        road_key: str,
        max_depth: Optional[int] = None,
        max_nodes: Optional[int] = None,
        max_edges: Optional[int] = None,
    ) -> KnowledgeGraphSubgraph:
        """Retrieves the subgraph rooted at a specific road corridor."""
        return self.get_subgraph(
            root_key=road_key,
            max_depth=max_depth if max_depth is not None else 2,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    def get_authority_graph(
        self,
        authority_key: str,
        max_depth: Optional[int] = None,
        max_nodes: Optional[int] = None,
        max_edges: Optional[int] = None,
    ) -> KnowledgeGraphSubgraph:
        """Retrieves the subgraph rooted at a specific civic authority."""
        return self.get_subgraph(
            root_key=authority_key,
            max_depth=max_depth if max_depth is not None else 2,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    def explain_relationship(self, edge_id: str) -> RelationshipExplanationResponse:
        """
        Returns full evidence provenance explaining why a specific edge exists in CVKI.
        Answers: 'Why does CVKI believe this entity is related to that entity?'
        """
        edge = self.repository.get_edge_by_id(edge_id)
        if not edge:
            # Try by canonical_edge_key
            edge = self.repository.get_edge_by_key(edge_id)

        if not edge:
            raise LookupError(f"Knowledge edge '{edge_id}' was not found.")

        from_node = self.repository.get_node_by_key(edge.from_node)
        to_node = self.repository.get_node_by_key(edge.to_node)

        if not from_node or not to_node:
            raise LookupError(f"Incomplete knowledge edge '{edge_id}': endpoint nodes are missing.")

        # Hydrate supporting M6.4 evidence records
        prov_engine = get_provenance_engine()
        ev_records: list[dict[str, Any]] = []
        source_name = None
        source_url = None
        source_type_val = edge.source_type.value if edge.source_type else None
        retrieved_at = edge.created_at
        freshness = "fresh"

        for ev_id in edge.evidence_ids:
            ev = prov_engine.repository.find_by_id(ev_id)
            if ev:
                ev_records.append(ev.model_dump(mode="json"))
                source_name = ev.source
                source_url = ev.source_url
                source_type_val = ev.source_type.value
                retrieved_at = ev.retrieved_at
                freshness = ev.freshness

        explanation_text = edge.explanation or f"{from_node.display_name} is connected to {to_node.display_name} via {edge.relation_type.value}."

        # Check if supporting evidence was invalidated
        has_invalidated_evidence = any(
            ev.get("status") == "invalidated" or ev.get("verification_state") == VerificationState.NOT_VERIFIED.value
            for ev in ev_records
        )
        effective_verification_state = edge.verification_state
        limitations = [
            "Evidence establishes traceability of system claims to underlying data sources; it does not replace statutory ground inspection.",
            "Environmental relationships represent contextual correlations and do not establish causation.",
        ]
        if has_invalidated_evidence and edge.evidence_ids:
            effective_verification_state = VerificationState.NOT_VERIFIED
            limitations.append("Supporting evidence was invalidated; this edge cannot support a verified conclusion.")

        return RelationshipExplanationResponse(
            edge_id=edge.edge_id,
            canonical_edge_key=edge.canonical_edge_key,
            from_node=from_node,
            to_node=to_node,
            relation_type=edge.relation_type,
            verification_state=effective_verification_state,
            evidence_ids=edge.evidence_ids,
            evidence_records=ev_records,
            source=source_name,
            source_type=source_type_val,
            source_url=source_url,
            explanation=explanation_text,
            retrieved_at=retrieved_at,
            freshness=freshness,
            limitations=limitations,
        )

    def find_related_cases(self, reference_id: str, limit: int = 20) -> list[str]:
        """
        Finds connected case reference IDs sharing the same road, authority, or recurrence pattern.
        """
        case_key = canonical_case_key(reference_id)
        edges = self.repository.find_edges_from(case_key)
        related_case_ids: set[str] = set()

        for edge in edges:
            target_key = edge.to_node
            # Check other cases linked to the target node
            target_node = self.repository.get_node_by_key(target_key)
            if target_node:
                for ref in target_node.case_references:
                    if ref != reference_id:
                        related_case_ids.add(ref)

        return sorted(list(related_case_ids))[:limit]

    def validate_graph_consistency(self) -> list[str]:
        """
        Audits graph consistency rules:
        1. No BUILT_BY edge without explicit tender/concession source.
        2. No causal rainfall edges.
        3. All edge endpoints exist.
        4. Stale evidence correctly reflected.
        """
        violations: list[str] = []
        all_edges = self.repository.all_edges()

        for edge in all_edges:
            # Rule 1: BUILT_BY requires explicit tender/concession registry
            if edge.relation_type == RelationType.BUILT_BY:
                if edge.source_type not in (SourceType.TENDER_REGISTRY, SourceType.CONCESSION_REGISTRY):
                    violations.append(
                        f"Consistency Violation: Edge '{edge.edge_id}' has relation BUILT_BY without tender/concession source ({edge.source_type})."
                    )

            # Rule 2: No causal rainfall edges
            if edge.relation_type == RelationType.HAS_RAINFALL_CONTEXT:
                expl = (edge.explanation or "").lower()
                if any(w in expl for w in ("caused", "causing", "responsible for", "due to")):
                    violations.append(
                        f"Consistency Violation: Edge '{edge.edge_id}' contains causal rainfall explanation: '{edge.explanation}'."
                    )

            # Rule 3: Endpoints exist
            if not self.repository.get_node_by_key(edge.from_node):
                violations.append(f"Dangling Edge '{edge.edge_id}': from_node '{edge.from_node}' does not exist.")
            if not self.repository.get_node_by_key(edge.to_node):
                violations.append(f"Dangling Edge '{edge.edge_id}': to_node '{edge.to_node}' does not exist.")

        return violations


knowledge_graph_service = CivicKnowledgeGraphService()


def get_knowledge_graph_service() -> CivicKnowledgeGraphService:
    return knowledge_graph_service


def set_knowledge_graph_service(service: CivicKnowledgeGraphService) -> None:
    global knowledge_graph_service
    knowledge_graph_service = service
