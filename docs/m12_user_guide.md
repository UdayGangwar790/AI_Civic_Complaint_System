# CVKI M12.7: User Operations Guide

This guide describes operational workflows for **Citizens**, **Municipal Authorities / Field Inspectors**, and **System Administrators** on the CVKI platform.

---

## 1. Important Operating Principles

> [!WARNING]
> - **CVKI is an Explainable Decision-Support System**: It does **not** replace municipal officials or field inspectors.
> - **Mandatory Human Acceptance**: All action playbooks, prioritization tiers, and dispatch suggestions require explicit review and authorization by an authorized municipal officer.
> - **No Autonomous Lifecycle Closure**: Cases cannot be automatically marked as physically resolved by algorithms alone.

---

## 2. Citizen User Journey

### Step 1: Reporting an Issue
1. Navigate to the Citizen Portal (`/report`).
2. Upload a clear photograph of the defect (supported classes: open manholes, damaged road signs, waterlogging, potholes, etc.).
3. Allow device GPS access or pin the defect location on the map.
4. Provide a description in your preferred language (English, Hindi, Hinglish, Kannada, Tamil, etc.).
5. The system performs instant client-side validation and generates a factual, neutral complaint summary.

### Step 2: Active Clarification (If Triggered)
- If your description and the photo disagree (for example, you mention "water leakage" but the model observes an "open manhole"), CVKI presents a single, targeted clarification prompt.
- Enter your clarification notes. Your response is recorded with epistemic designation `USER_REPORTED` and attached directly to the case dossier.

### Step 3: Tracking Your Case
- Receive a unique reference ID (e.g., `CVKI-20261019-A48F9B`).
- Track case progress, maintenance authority assignment, and field inspection milestones in real time.

---

## 3. Municipal Authority & Field Inspector Workflow

### Step 1: Authority Triage Dashboard
1. Log in with your authorized municipal credentials (`AUTHORITY` role).
2. The dashboard filters cases strictly within your assigned jurisdiction (e.g., BBMP, Delhi MCD, NHAI).
3. Review the **Priority Score (0–100)** computed from defect severity, road classification, traffic corridor importance, and recent local recurrence.

### Step 2: Decision Support & Action Playbook Review
1. Open the case details view.
2. Examine the recommended **Operational Action Playbooks** (e.g., immediate barricade, asphalt cold patch, drain cleaning).
3. Review the verified evidence, weather context, and knowledge graph relationships.
4. Select your review disposition:
   - `ACCEPTED`: Adopt the recommended playbook.
   - `MODIFIED`: Adjust the equipment or work crew requirements.
   - `REJECTED`: Dismiss the recommendation with required justification notes.

### Step 3: Generating Field Inspection Protocol
1. Click **Generate Inspection Protocol** to build a structured, step-by-step physical verification checklist.
2. The protocol automatically embeds geofenced boundary coordinates centered on the reported defect.

### Step 4: Field Inspection Execution & Audit
1. The field inspector visits the site and submits observations for each checklist step.
2. The inspector submits real-time coordinates and after-repair verification photos.
3. The CVKI **Field Inspection Audit Engine** audits the submission:
   - Verifies the inspector was physically inside the designated geofence.
   - Verifies all mandatory checklist steps were observed.
   - Outputs an audit result (`SUPPORTED`, `INCONCLUSIVE`, or `CONTRADICTED`).

---

## 4. Administrator Operations

1. **Hotspot & Recurrence Analytics**:
   - Inspect 30-day spatial clustering and 180-day recurrence corridors to identify chronically failing infrastructure assets.
2. **Authority Assignment Management**:
   - Resolve jurisdictional boundary disputes and reassign cases between municipal and state authorities.
3. **Cryptographic Provenance Audit**:
   - Inspect the tamper-evident SHA-256 evidence chain for any case to review full historical lineage from submission through resolution.
