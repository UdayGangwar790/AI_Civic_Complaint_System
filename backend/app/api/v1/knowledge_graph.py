import logging
from typing import Optional
from urllib.parse import unquote
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.api.deps import AuthenticatedUser, get_current_user
from app.models.roles import UserRole
from app.schemas.knowledge_graph import (
    KnowledgeGraphSubgraph,
    NodeType,
    RelationshipExplanationResponse,
)
import app.services.complaint_case as complaint_case_module
from app.services.knowledge_graph import get_knowledge_graph_service

logger = logging.getLogger("cvki.api.knowledge_graph")

router = APIRouter()
_graph_rate_limit = Depends(
    rate_limit_dependency(
        scope="knowledge_graph",
        limit=settings.EXPENSIVE_SEARCH_RATE_LIMIT_REQUESTS,
        window_seconds=settings.EXPENSIVE_SEARCH_RATE_LIMIT_WINDOW_SECONDS,
    )
)


def _sanitize_subgraph_for_citizen(subgraph: KnowledgeGraphSubgraph) -> KnowledgeGraphSubgraph:
    """
    Sanitizes privacy-sensitive user identifiers and private notes from graph nodes and edges
    when requested by citizen roles.
    """
    sanitized_nodes = []
    for node in subgraph.nodes:
        # Exclude internal user actor nodes from citizen view or mask them
        if node.node_type == NodeType.USER_ACTOR:
            continue
        n_copy = node.model_copy(deep=True)
        # Strip internal PII
        n_copy.metadata.pop("user_id", None)
        n_copy.metadata.pop("email", None)
        n_copy.metadata.pop("phone", None)
        n_copy.metadata.pop("assigned_to_user_id", None)
        n_copy.metadata.pop("internal_notes", None)
        sanitized_nodes.append(n_copy)

    sanitized_node_ids = {n.canonical_key for n in sanitized_nodes}

    sanitized_edges = []
    for edge in subgraph.edges:
        # If an edge connects to a filtered node, omit it
        if edge.from_node not in sanitized_node_ids or edge.to_node not in sanitized_node_ids:
            continue
        e_copy = edge.model_copy(deep=True)
        e_copy.metadata.pop("user_id", None)
        e_copy.metadata.pop("email", None)
        e_copy.metadata.pop("assigned_to_user_id", None)
        sanitized_edges.append(e_copy)

    return KnowledgeGraphSubgraph(
        root_node_key=subgraph.root_node_key,
        nodes=sanitized_nodes,
        edges=sanitized_edges,
        total_nodes=len(sanitized_nodes),
        total_edges=len(sanitized_edges),
        max_depth_reached=subgraph.max_depth_reached,
        generated_at=subgraph.generated_at,
        limitations=subgraph.limitations,
    )


@router.get(
    "/cases/{reference_id}",
    response_model=KnowledgeGraphSubgraph,
    summary="Get bounded civic knowledge graph for a complaint case",
    dependencies=[_graph_rate_limit],
)
async def get_case_knowledge_graph(
    reference_id: str,
    max_depth: Optional[int] = Query(None, ge=1, le=8, description="Maximum traversal depth (default 4)"),
    max_nodes: Optional[int] = Query(None, ge=1, le=500, description="Maximum nodes returned (default 200)"),
    max_edges: Optional[int] = Query(None, ge=1, le=1000, description="Maximum edges returned (default 500)"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> KnowledgeGraphSubgraph:
    """
    Retrieves the connected Civic Knowledge Graph subgraph for a case.
    Strictly enforces RBAC:
    - Citizen: only accessible for their own cases (403 for others).
    - Authority: only accessible for assigned cases within their authority scope (403 for unassigned).
    - Admin: unrestricted access.
    """
    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    # 1. Authority RBAC
    if current_user.role == UserRole.AUTHORITY.value:
        assigned_user_id = case.assignment.assigned_to_user_id if case.assignment else None
        if assigned_user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authorities can only view the knowledge graph for cases assigned to them.",
            )

    # 2. Citizen RBAC
    elif current_user.role == UserRole.CITIZEN.value:
        if case.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Citizens can only view the knowledge graph for their own cases.",
            )

    # 3. Fetch or construct graph
    kg_service = get_knowledge_graph_service()
    subgraph = kg_service.get_case_graph(
        reference_id=reference_id,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )

    # If the case graph is empty or missing, build it dynamically from the case record
    if not subgraph.nodes:
        kg_service.build_case_graph(case)
        subgraph = kg_service.get_case_graph(
            reference_id=reference_id,
            max_depth=max_depth,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    if current_user.role == UserRole.CITIZEN.value:
        return _sanitize_subgraph_for_citizen(subgraph)

    return subgraph


@router.post(
    "/cases/{reference_id}/rebuild",
    response_model=KnowledgeGraphSubgraph,
    summary="Deterministically rebuild the knowledge graph for a complaint case",
)
async def rebuild_case_knowledge_graph(
    reference_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> KnowledgeGraphSubgraph:
    """
    Deterministically rebuilds the knowledge graph for an existing case from its current persisted data.
    Restricted to Authority and Admin roles.
    """
    if current_user.role == UserRole.CITIZEN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Citizens cannot trigger knowledge graph rebuilds.",
        )

    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    if current_user.role == UserRole.AUTHORITY.value:
        assigned_user_id = case.assignment.assigned_to_user_id if case.assignment else None
        if assigned_user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authorities can only rebuild knowledge graph for cases assigned to them.",
            )

    kg_service = get_knowledge_graph_service()
    subgraph = kg_service.rebuild_case_graph(reference_id, case=case)
    return subgraph


@router.get(
    "/roads/{road_key:path}",
    response_model=KnowledgeGraphSubgraph,
    summary="Get bounded knowledge graph subgraph for a road",
)
async def get_road_knowledge_graph(
    road_key: str,
    max_depth: Optional[int] = Query(None, ge=1, le=6),
    max_nodes: Optional[int] = Query(None, ge=1, le=500),
    max_edges: Optional[int] = Query(None, ge=1, le=1000),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> KnowledgeGraphSubgraph:
    """
    Retrieves the connected knowledge graph for a canonical road key (e.g. road:nh_44:bengaluru).
    """
    clean_key = unquote(road_key)
    kg_service = get_knowledge_graph_service()
    subgraph = kg_service.get_road_graph(
        road_key=clean_key,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )

    if not subgraph.nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Road node '{clean_key}' was not found in the civic knowledge graph.",
        )

    if current_user.role == UserRole.CITIZEN.value:
        return _sanitize_subgraph_for_citizen(subgraph)

    return subgraph


@router.get(
    "/authorities/{authority_key:path}",
    response_model=KnowledgeGraphSubgraph,
    summary="Get bounded knowledge graph subgraph for a maintenance authority",
)
async def get_authority_knowledge_graph(
    authority_key: str,
    max_depth: Optional[int] = Query(None, ge=1, le=6),
    max_nodes: Optional[int] = Query(None, ge=1, le=500),
    max_edges: Optional[int] = Query(None, ge=1, le=1000),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> KnowledgeGraphSubgraph:
    """
    Retrieves the connected knowledge graph for an authority key (e.g. authority:bbmp).
    Enforces scope checks for authority users.
    """
    clean_key = unquote(authority_key)

    # Authority scope check
    if current_user.role == UserRole.AUTHORITY.value:
        # If user has specific authority tag, ensure they cannot inspect rival authority graph internals
        authority_scope = (current_user.metadata or {}).get("authority_key") if hasattr(current_user, "metadata") else None
        if authority_scope and clean_key != authority_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authorities can only query their own authority knowledge graph scope.",
            )

    kg_service = get_knowledge_graph_service()
    subgraph = kg_service.get_authority_graph(
        authority_key=clean_key,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )

    if not subgraph.nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Authority node '{clean_key}' was not found in the civic knowledge graph.",
        )

    if current_user.role == UserRole.CITIZEN.value:
        return _sanitize_subgraph_for_citizen(subgraph)

    return subgraph


@router.get(
    "/relationships/{edge_id}",
    response_model=RelationshipExplanationResponse,
    summary="Explain a specific knowledge graph relationship with supporting evidence",
)
async def explain_relationship(
    edge_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> RelationshipExplanationResponse:
    """
    Explains the provenance, evidence, and verification backing a specific relationship edge in the graph.
    Answers: 'Why does CVKI believe this entity relates to that entity?'
    """
    kg_service = get_knowledge_graph_service()
    explanation = kg_service.explain_relationship(edge_id)

    if not explanation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge graph relationship '{edge_id}' was not found.",
        )

    # RBAC check: If edge is associated with a specific case
    if current_user.role == UserRole.CITIZEN.value:
        edge = kg_service.repository.get_edge_by_id(edge_id)
        if edge and edge.case_reference:
            try:
                case = await complaint_case_module.get_case(edge.case_reference)
                if case.user_id != current_user.user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Citizens cannot inspect relationship details of other citizens' cases.",
                    )
            except complaint_case_module.ComplaintCaseNotFoundError:
                pass

    return explanation


@router.get(
    "/cases/{reference_id}/related",
    response_model=list[str],
    summary="Find related case reference IDs sharing roads, authorities, or recurrence patterns",
)
async def find_related_cases(
    reference_id: str,
    limit: int = Query(10, ge=1, le=50),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[str]:
    """
    Traverses connected graph nodes (same road, authority, or hotspot) to identify related case references.
    """
    try:
        case = await complaint_case_module.get_case(reference_id)
    except complaint_case_module.ComplaintCaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint case '{reference_id}' was not found.",
        )

    if current_user.role == UserRole.CITIZEN.value and case.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Citizens can only query related cases for their own complaint cases.",
        )

    kg_service = get_knowledge_graph_service()
    return kg_service.find_related_cases(reference_id=reference_id, limit=limit)
