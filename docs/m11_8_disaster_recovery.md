# CVKI M11.8 Disaster Recovery & Backup Readiness Specification

## 1. Executive Summary & Operational Scope

This document establishes the official disaster recovery, business continuity, and data preservation framework for the **Civic Vision & Knowledge Intelligence (CVKI)** platform. It details operational procedures for failure scenarios including database corruption, instance termination, configuration loss, and external integration state discrepancies.

> [!IMPORTANT]
> **Operational Status Disclosure:**
> Unless explicitly noted otherwise, continuous cloud backups, multi-region replication, and automated snapshot schedulers are classified as:
> **STATUS: RECOMMENDED / NOT CONFIGURED IN LOCAL ENVIRONMENT**
> All recovery scripts, deterministic validation suites, and manual restore protocols detailed herein are designed for production deployment and verified against disposable test fixtures.

---

## 2. Recovery Objectives (RPO & RTO)

| Metric | Target Window | Local Environment Status | Notes |
| :--- | :--- | :--- | :--- |
| **RPO (Recovery Point Objective)** | < 1 hour | **NOT CONFIGURED** (Point-in-time oplog archiving not configured locally) | Production target requires MongoDB Atlas continuous backup or daily `mongodump` + 15-minute oplog slice archiving. |
| **RTO (Recovery Time Objective)** | < 30 minutes | **VERIFIED** via deterministic local test harness | Restoration of complete collections and index rebuilding takes < 15 seconds for engineering databases. |

---

## 3. Subsystem Backup Strategies

### 3.1 MongoDB Primary Persistence Layer
* **Authoritative Collections:**
  - `complaint_cases` (Case lifecycle, coordinates, priority analysis, assignments)
  - `users` (RBAC identities, hashed credentials, role bindings)
  - `notifications` (Citizen and authority event dispatch history)
  - `audit_logs` (Security events, access checks, administrative actions)
  - `government_submissions` & `government_reference_mappings` (Official civic portal dispatches)
  - `resolution_verifications` (Citizen and inspector verification records)
  - `authority_cache`, `geo_cache`, `external_civic_cache` (Ephemeral caching tiers)

* **Backup Methodology (Recommended Production Standard):**
  ```bash
  # Daily Compressed Binary Dump with Oplog
  mongodump --uri="${MONGODB_URI}" --gzip --archive=/backups/cvki_mongo_$(date +%Y%m%d_%H%M%S).gz --oplog
  ```
* **Retention Policy:**
  - Hourly snapshots retained for 48 hours.
  - Daily archives retained for 30 days.
  - Monthly archives retained for 1 year in cold, immutably locked cloud storage (WORM policy).

### 3.2 Evidence Provenance Engine (`evidence_records`)
* **Criticality:** High.
* **Integrity Mechanism:** Cryptographic hash-chaining (`evidence_hash` computed over `parent_hash`, `timestamp`, `source`, `claim_value`).
* **Preservation Strategy:**
  - Exported alongside primary database dump.
  - Periodic JSONL export with cumulative Merkle root calculation.
  - If a provenance record is corrupted, the integrity check alerts immediately on restore.

### 3.3 Civic Knowledge Graph (`knowledge_nodes`, `knowledge_edges`)
* **Criticality:** High.
* **Recovery Mechanism:**
  - Primary: Restored from MongoDB dump.
  - Secondary (Self-Healing / Projection): If the graph collection suffers partial corruption, the Knowledge Graph is **deterministically re-projectable** from the primary `complaint_cases`, `field_inspection`, and `evidence_records` using:
    ```python
    kg_service.rebuild_case_graph(reference_id=case.reference_id)
    ```

### 3.4 Frozen Model & Vision Dataset Preservation
* **Authoritative Assets:**
  - Frozen weights: `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt`
  - SHA-256 Checksum: `602160d4851e0d79c34cf23b828bde474fc4c164eaf1a1c2a884cfb372f4bda3`
  - Dataset: `ai/computer_vision/dataset_m1_13` (605 files)
* **Preservation Status:**
  - Read-only storage.
  - Weights and dataset are version-controlled and cryptographically validated on application startup.
  - No database backup is required for model weights as they exist immutably in source repository artifacts.

---

## 4. Deterministic Restore Validation Procedure

In the event of database failure or corrupted state, the following sequence must be executed:

### Step 1: Pre-Restore Verification & Environment Quarantine
1. Verify target host environment and disconnect inbound traffic:
   ```bash
   # Isolate traffic or put backend in maintenance mode
   export MAINTENANCE_MODE=true
   ```
2. Verify integrity of backup archive (check GZIP magic bytes and archive checksum).

### Step 2: Database Restoration
```bash
# Restore directly with drop to prevent collision
mongorestore --uri="${MONGODB_RESTORE_URI}" --gzip --archive=/backups/target_backup.gz --drop
```

### Step 3: Index Integrity Verification
Ensure all required unique constraints and geospatial 2dsphere indexes are reconstructed:
```python
from app.core.database import init_mongo_indexes, get_database
db = get_database()
await init_mongo_indexes(db)
```

### Step 4: Cryptographic Provenance Hash-Chain Validation
Execute verification across all restored cases:
```python
from app.services.provenance_engine import get_provenance_engine
prov_engine = get_provenance_engine()
is_valid, reason = prov_engine.verify_chain_integrity(case_reference)
assert is_valid, f"Provenance hash chain verification failed: {reason}"
```

### Step 5: Knowledge Graph Projection Consistency Check
Verify that all active cases have corresponding canonical root nodes in `knowledge_nodes`:
```python
from app.services.knowledge_graph import get_knowledge_graph_service
kg = get_knowledge_graph_service()
node = kg.get_node(f"case:{case_reference}")
assert node is not None, f"Missing knowledge graph root node for {case_reference}"
```

### Step 6: Post-Restore Readiness Validation
Perform health checks against `/api/health/ready` to ensure database readiness and model availability before returning the instance to service.

---

## 5. Secret & Configuration Recovery Procedure

* **Environment Variables:**
  - Production configurations are managed via secret injection (e.g. HashiCorp Vault, AWS Secrets Manager, or Doppler).
  - The local repository maintains `.env.example` as a template with zero credentials.
* **Key Rotation & Loss Protocol:**
  - If `JWT_SECRET` is compromised or lost: Generate a new 32+ character entropy string, invalidate existing active sessions by forcing re-login (active JWTs signed with previous secret become invalid upon signature verification failure).
  - If `CPGRAMS_API_KEY` is revoked: Regenerate on DARPG portal, update environment secret, restart service.

---

## 6. Disaster Recovery Test Log & Validation

* **Test Date:** October 2026
* **Harness:** Disposable test collections in local environment.
* **Result:**
  - Database schema restoration: PASS.
  - Unique index restoration (`reference_id`, `user_id`, `email`, `evidence_id`, `canonical_key`): PASS.
  - Provenance hash-chain verification post-restore: PASS (0 broken chains).
  - Idempotency store isolation post-restore: PASS.
