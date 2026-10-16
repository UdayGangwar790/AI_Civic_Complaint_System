# Module M6.5: Civic Knowledge Graph

## 1. Executive Summary & Epistemological Boundary

> **Core System Principle:**
> *"The knowledge graph is an integration and explainability layer. It connects verified system claims with explicit uncertainty and does not independently establish the truth of underlying external claims."*

Module M6.5 introduces a modular, server-authoritative **Civic Knowledge Graph** for the CVKI platform. The knowledge graph sits as an integration and explainability layer over Persisted Case records, Computer Vision Detections (M1.13), Authority Intelligence (M6.1), Geospatial Context (M6.2), Real-Time External Civic Data (M6.3), Evidence Provenance Engine (M6.4), Recurrence & Hotspots (M5.2), and Complaint Lifecycle & Resolution records.

The graph does not duplicate business documents or introduce heavy external graph databases (e.g. Neo4j). Instead, it implements a normalized, MongoDB-compatible graph storage architecture (`knowledge_nodes` and `knowledge_edges`) with complete in-memory fallback for local execution and fast deterministic queries.

```
                    ┌─────────────────────────┐
                    │       Civic Issue       │
                    └────────────┬────────────┘
                                 │ DETECTED_AS
                                 ▼
                    ┌─────────────────────────┐
                    │     Detection Event     │
                    └────────────┬────────────┘
                                 │ LOCATED_AT
                                 ▼
                    ┌─────────────────────────┐
                    │      Location Point     │
                    └────────────┬────────────┘
                                 │ ON_ROAD
                                 ▼
                    ┌─────────────────────────┐
                    │     Road Corridor       │
                    └──────┬────────────┬─────┘
          WITHIN_JURISDICTION │            │ MAINTAINED_BY / OWNED_BY
                           │            │
                           ▼            ▼
             ┌─────────────────┐    ┌─────────────────────────┐
             │  Jurisdiction   │    │  Maintenance Authority  │
             └─────────────────┘    └───────────┬─────────────┘
                                                │ BUILT_BY (Strict Tender Only)
                                                ▼
                                    ┌─────────────────────────┐
                                    │  Builder / Contractor   │
                                    └─────────────────────────┘
                                                │
                                                ▼
    ┌────────────────────────────────────────────────────────────────────────┐
    │ Contextual & Historical Augmentations:                                 │
    │  - HAS_WEATHER_CONTEXT (live / cached)                                 │
    │  - HAS_RAINFALL_CONTEXT (non-causal environmental correlation)         │
    │  - RECURRENCE_OF (180-day window, 250m spatial radius, system-derived) │
    │  - PART_OF_HOTSPOT (cluster density, system-derived)                   │
    │  - DUPLICATE_OF (spatiotemporal heuristic match)                       │
    │  - HAS_COMPLAINT & HAS_RESOLUTION (lifecycle evidence traceability)    │
    └────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Graph Storage Strategy & Schemas

### 2.1 Collections
The graph persistence relies on two collections indexed in MongoDB:
1. `knowledge_nodes`: Persists normalized entities with canonical identities.
2. `knowledge_edges`: Persists directed relationships with verification states, evidence references, and provenance traceability.

### 2.2 Node Model (`KnowledgeNode`)
```json
{
  "node_id": "node_7e52a46618484a",
  "node_type": "road",
  "canonical_key": "road:mg_road:bengaluru",
  "display_name": "MG Road",
  "case_references": ["CIV-2026-1001", "CIV-2026-1002"],
  "metadata": {
    "city": "Bengaluru",
    "district": "Bengaluru Urban",
    "state": "Karnataka"
  },
  "created_at": "2026-10-14T21:00:00Z",
  "updated_at": "2026-10-14T21:05:00Z"
}
```

**Supported Node Types (20 total):**
- `civic_issue`: High-level defect taxonomy category (e.g. pothole, street_light).
- `detection`: Specific CV detection event with confidence score.
- `case`: Root complaint case record.
- `location`: Geodetic spatial point bucketed to 4 decimal places (~11m).
- `road`: Named road corridor.
- `road_segment`: Segmented division of a road corridor.
- `jurisdiction`: Administrative boundary (ward, division, municipal corporation).
- `road_owner`: Sovereign asset owner entity.
- `maintenance_authority`: Statutory maintenance responsibility body.
- `builder_or_contractor`: Construction contractor (strictly guarded by tender proof).
- `evidence`: Supporting provenance record.
- `weather_context`: In-situ ambient temperature and atmospheric conditions.
- `rainfall_context`: Non-causal precipitation depth and intensity correlation.
- `traffic_context`: Corridor congestion observation.
- `recurrence_pattern`: Historical recurring civic incident cluster (180d window).
- `hotspot`: City-wide defect cluster concentration.
- `complaint`: Structured citizen filing package.
- `resolution`: Formal verification of defect repair.
- `source`: Official registry, open data endpoint, or model source.
- `user_actor`: Internal workflow actor (scrubbed from public views).

### 2.3 Edge Model (`KnowledgeEdge`)
```json
{
  "edge_id": "edge_3f890c29be01",
  "canonical_edge_key": "edge:road:mg_road:bengaluru:MAINTAINED_BY:authority:bbmp",
  "from_node": "road:mg_road:bengaluru",
  "to_node": "authority:bbmp",
  "relation_type": "MAINTAINED_BY",
  "evidence_ids": ["ev_543c7b89d412"],
  "verification_state": "verified",
  "source_type": "government_registry",
  "case_reference": "CIV-2026-1001",
  "explanation": "Maintenance responsibility assigned to BBMP per Master Road Registry.",
  "metadata": {},
  "created_at": "2026-10-14T21:00:00Z",
  "updated_at": "2026-10-14T21:00:00Z"
}
```

**Supported Relation Types (24 total):**
`DETECTED_AS`, `LOCATED_AT`, `ON_ROAD`, `ON_ROAD_SEGMENT`, `WITHIN_JURISDICTION`, `OWNED_BY`, `MAINTAINED_BY`, `BUILT_BY`, `SUPPORTED_BY`, `SOURCED_FROM`, `HAS_EXTERNAL_CONTEXT`, `HAS_WEATHER_CONTEXT`, `HAS_RAINFALL_CONTEXT`, `HAS_TRAFFIC_CONTEXT`, `RECURRENCE_OF`, `PART_OF_HOTSPOT`, `DUPLICATE_OF`, `RELATED_TO`, `HAS_COMPLAINT`, `HAS_RESOLUTION`, `RESOLVED_BY`, `ASSIGNED_TO`, `SUBMITTED_TO`, `GENERATED_FROM`.

---

## 3. Canonical Identifiers

Every entity in the graph possesses a deterministic canonical key. This ensures idempotent construction and deduplication across multiple case rebuilds:

| Entity Type | Canonical Key Format | Example |
|---|---|---|
| Case | `case:<ref_id>` | `case:CIV-2026-0042` |
| Road | `road:<normalized_road>:<normalized_city>` | `road:mg_road:bengaluru` |
| Location | `location:<lat_4dec>:<lon_4dec>` | `location:12.9716:77.5947` |
| Jurisdiction | `jurisdiction:<normalized_name>[:<level>]` | `jurisdiction:bengaluru_urban` |
| Authority | `authority:<normalized_name>` | `authority:bbmp` |
| Builder | `builder:<normalized_name>` | `builder:larsen_and_toubro_ltd` |
| Weather | `weather:<provider>:<lat_2dec>:<lon_2dec>` | `weather:open_meteo:12.97:77.59` |
| Rainfall | `rainfall:<provider>:<lat_2dec>:<lon_2dec>` | `rainfall:imd:12.97:77.59` |
| Edge | `edge:<from_key>:<relation>:<to_key>` | `edge:road:mg_road:bengaluru:MAINTAINED_BY:authority:bbmp` |

*Note on Coordinates:* Raw floating-point coordinates are strictly forbidden as canonical keys due to IEEE-754 precision drift. Location keys are bucketed to 4 decimal places (~11 meters), ensuring reliable spatial identity.

---

## 4. Verification-Aware Architecture & Provenance Integration

Every edge carries an explicit `verification_state`:
- `verified`: Grounded in authoritative, active, unexpired official records (e.g. BBMP Master Road Register, official gazette).
- `partially_verified`: Grounded in heuristics, cached entries, or approximate geospatial matches.
- `not_verified`: Claim exists as an unverified filing or unconfirmed report.
- `system_derived`: Deterministically produced by CVKI intelligence engines (recurrence, hotspot, spatiotemporal clustering).

**Key Guarantees:**
1. The graph **never promotes** an unverified relationship to `verified` merely because an edge connects two entities.
2. An edge references M6.4 `evidence_ids`. It does not clone full evidence blobs into relationship edges.
3. If an evidence record is invalidated in M6.4, it cannot support a `verified` relationship edge.

---

## 5. Strict Consistency & Safety Rules

1. **Builder Safety (Anti-Inference Guard):**
   `BUILT_BY` edges are **strictly forbidden** to be inferred from `MAINTAINED_BY` or `OWNED_BY`. A `BUILT_BY` edge is created **only** when supported by an explicit tender, concession, contract, or project registry record (`SourceType.TENDER_REGISTRY` or `SourceType.CONCESSION_REGISTRY`).
2. **Non-Causal Environmental Correlation:**
   Precipitation is linked via `HAS_RAINFALL_CONTEXT` only. The graph **never creates causal edges** (e.g. `RAINFALL -> CAUSED -> WATERLOGGING`). Explanations are audited by `validate_graph_consistency()` to guarantee absence of causal claims.
3. **No Fabricated Entities:**
   If road identification is unavailable from M6.2 geocoders, no placeholder or fake road node is created.
4. **Server-Authoritative Construction:**
   Graph construction is entirely server-driven; client input cannot establish or modify graph nodes or relationships.

---

## 6. Graph Synchronization & Rebuild Idempotency

### Deterministic Rebuild
When case data changes or an authority rebuilds a case graph:
```python
subgraph = kg_service.rebuild_case_graph(reference_id)
```
1. Stale case-specific edges are cleanly removed via `delete_case_edges(reference_id)`.
2. Shared nodes (such as the road corridor or maintenance authority) are preserved, while updating case linkage lists (`case_references`).
3. Relationships are reconstructed from persisted case records.
4. Determinism invariant: `rebuild_case_graph(ref)` called $N$ times yields byte-for-byte identical canonical keys and edge sets.

---

## 7. Traversal Bounds & Anti-Runaway Protection

All subgraph queries enforce strict bounds to prevent unbounded recursion or denial-of-service:
- `GRAPH_MAX_DEPTH`: default `4` (maximum allowed `8`).
- `GRAPH_MAX_NODES`: default `200` (maximum allowed `500`).
- `GRAPH_MAX_EDGES`: default `500` (maximum allowed `1000`).

Breadth-first search traversal terminates immediately when any limit is reached, recording `max_depth_reached` on the returned `KnowledgeGraphSubgraph`.

---

## 8. API Specifications & RBAC

All endpoints reside under `/api/v1/knowledge-graph`:

| Endpoint | Method | Role Permissions | Description |
|---|---|---|---|
| `/cases/{reference_id}` | GET | Citizen (own case), Authority (assigned), Admin | Returns bounded case subgraph with citizen privacy scrub. |
| `/cases/{reference_id}/rebuild` | POST | Authority (assigned), Admin | Deterministically clears and rebuilds case graph. |
| `/roads/{road_key}` | GET | Authenticated Users | Returns road corridor subgraph. |
| `/authorities/{authority_key}` | GET | Authority (own scope), Admin | Returns maintenance authority subgraph. |
| `/relationships/{edge_id}` | GET | Authenticated Users | Hydrates relationship explainability inspector. |
| `/cases/{reference_id}/related` | GET | Citizen (own case), Authority, Admin | Finds connected cases sharing roads or recurrence. |

### Privacy Scrubbing for Citizens:
When requested by a Citizen:
- `USER_ACTOR` nodes are omitted.
- Sensitive fields (`email`, `user_id`, `phone`, `internal_notes`, `assigned_to_user_id`) are stripped from node and edge metadata.

---

## 9. Frontend Relationship Explorer & Topology

Implemented in `frontend/src/components/KnowledgeGraphPanel.jsx`:
- **Relationship Explorer View:** Clean, chronological display of connected entity cards (`From Entity -> Relation Type -> To Entity`) with verification status badges.
- **Explain Link Action:** Clicking any edge opens the **Relationship Explainability Inspector**, detailing:
  - From and To entities.
  - Relation Type.
  - Verification State badge.
  - Source & Source Type.
  - Supporting Evidence IDs.
  - Epistemological caveats and plain-language explanation.
- **Visual Topology View (Staff/Admin):** Interactive SVG topology view depicting entity nodes (color-coded by type) and directed relationship links.
- **Rebuild Action:** One-click deterministic rebuild for staff/admins.
- **Epistemological Disclaimer Footer:** Displayed on all views to preserve interpretative clarity.

---

## 10. Verification & Regression Results

- **Unit & Integration Suite (`test_civic_knowledge_graph_m65.py`):** 36/36 tests passed covering sections A through AJ.
- **M5 & M6 Integration Suite:** 144/144 tests passed across M6.5, M6.4, M6.3, M6.2, M6.1, and M5.2.
- **Frontend Build & Lint:** Clean build via Vite (2.35s) with 0 errors.
- **Frozen YOLO Model SHA-256:**
  `602160D4851E0D79C34CB23B828BDE474FC4C164EAF1A1C2A884CFB372F4BDA3` (Exact match).
