# M3.10 Government Dispatch / Submission Preparation

## Overview
Module **M3.10** implements a safe, verifiable government submission preparation layer for Civic Vision & Knowledge Intelligence (CVKI) complaint cases. It transforms verified complaint case records into standardized government dispatch packages while strictly enforcing external submission safety boundaries.

---

## Critical Safety & Compliance Principles

1. **Explicit Separation Between Case Creation and Government Dispatch:**
   - CVKI case registration (`status = submitted`) represents internal platform intake.
   - Government submission status strictly remains `NOT_SUBMITTED`.
   - Preparation produces a structured draft package for review, but **never** performs automatic or unauthorized submissions.

2. **No Web Scraping or Portal Automation:**
   - CVKI does NOT attempt to automate government portal actions, bypass CAPTCHA, or simulate authenticated sessions on external government portals.

3. **No Fabrication of Details:**
   - No fabricated government reference, docket, or token numbers.
   - No fabricated department names, phone numbers, or guessed URLs.
   - Contractor/builder information is only included if explicitly attested by official government open-data sources.

---

## Submission Readiness Evaluation

The `check_submission_readiness` service inspects cases across multiple safety gates:

| Readiness Status | Trigger Conditions | Permitted Action |
| :--- | :--- | :--- |
| `ready` | Complaint details complete, location coordinates and road/area present, authority is `verified` by official government records. | Can prepare authority-specific dispatch package. |
| `partially_ready` | Complaint details and location present, but authority is `partially_verified`. | Can prepare package marked as `review_required = True`. |
| `not_ready` | Missing mandatory fields (e.g. blank description, missing coordinates, or missing authority). | Preparation prevented until missing fields are resolved. |
| `blocked` | Authority is `not_verified` or blocked due to contradictory evidence. | Preparation blocked. System states that official authority could not be verified. |

---

## Structured Submission Package Schema

When prepared, the package is nested under `complaint_case.government_submission`:

```json
{
  "readiness_status": "ready",
  "submission_status": "NOT_SUBMITTED",
  "prepared_at": "2026-10-11T17:15:30.123456Z",
  "authority_status": "verified",
  "review_required": false,
  "package": {
    "cvki_reference_id": "CVKI-20261011-B61A9C",
    "issue_category": "pothole",
    "complaint_title": "Severe road pothole on MG Road",
    "complaint_description": "Large deep pothole causing traffic slowdown and safety hazard near metro pillar.",
    "location": {
      "latitude": 12.9716,
      "longitude": 77.5946,
      "road": "MG Road",
      "area": "Shanthala Nagar",
      "city": "Bengaluru",
      "district": "Bengaluru Urban",
      "state": "Karnataka",
      "country": "India"
    },
    "authority_verification_state": "verified",
    "road_owner": "Bruhat Bengaluru Mahanagara Palike (BBMP)",
    "maintenance_authority": "Bruhat Bengaluru Mahanagara Palike (BBMP)",
    "builder_or_contractor": null,
    "official_evidence_records": [
      {
        "source": "BBMP Official Road Inventory",
        "jurisdiction": "Bengaluru Central",
        "official_source_url": "https://bbmp.gov.in"
      }
    ],
    "priority": {
      "priority_level": "P1",
      "priority_score": 88,
      "risk_level": "Critical"
    },
    "nlp_analysis_summary": {
      "language": "en",
      "issue_category": "pothole",
      "severity_signals": ["deep", "severe"]
    },
    "duplicate_status": "unique",
    "created_at": "2026-10-11T17:10:00.000000Z",
    "prepared_at": "2026-10-11T17:15:30.123456Z",
    "submission_status": "NOT_SUBMITTED"
  },
  "official_sources": [
    {
      "source_name": "BBMP Portal",
      "domain": "bbmp.gov.in",
      "url": "https://bbmp.gov.in"
    }
  ],
  "limitations": [
    "Package prepared for human review and manual dispatch. Automated external submission is disabled.",
    "External government submission status remains NOT_SUBMITTED until processed via verified government integration."
  ]
}
```

---

## REST API Endpoints

### 1. Check Submission Readiness
`GET /api/v1/complaint/cases/{reference_id}/submission-readiness`
- **Security:** Requires authenticated JWT matching the case creator (`user_id`).
- **Response:**
```json
{
  "reference_id": "CVKI-20261011-B61A9C",
  "readiness_status": "ready",
  "submission_status": "NOT_SUBMITTED",
  "authority_status": "verified",
  "reasons": [
    "Complaint description and issue category verified.",
    "Location coordinates and road details complete.",
    "Responsible authority verified via official government records."
  ],
  "missing_fields": [],
  "official_sources": [
    {
      "source_name": "BBMP Official Portal",
      "domain": "bbmp.gov.in",
      "url": "https://bbmp.gov.in"
    }
  ],
  "limitations": [
    "CVKI evaluates technical readiness for dispatch preparation only. External submission remains NOT_SUBMITTED."
  ]
}
```

### 2. Prepare Government Submission Package
`POST /api/v1/complaint/cases/{reference_id}/prepare-submission`
- **Security:** Requires authenticated JWT matching the case creator.
- **Side Effect:** Persists the prepared package in MongoDB under `government_submission` and emits an in-app notification of type `government_submission_prepared`.
- **Response:**
```json
{
  "reference_id": "CVKI-20261011-B61A9C",
  "submission_status": "NOT_SUBMITTED",
  "readiness_status": "ready",
  "prepared_at": "2026-10-11T17:15:30.123456Z",
  "authority": {
    "road_owner": "BBMP",
    "maintenance_authority": "BBMP",
    "authority_status": "verified"
  },
  "package": { ... },
  "limitations": [ ... ]
}
```

---

## Frontend Integration
- **Case Detail Modal:** Includes a dedicated "Government Dispatch & Submission Preparation" card.
- **Status Indicator Badges:**
  - `CVKI Case: Submitted to CVKI`
  - `Government Submission: Not Submitted`
  - Readiness Pill (`Ready` / `Review Required` / `Not Ready` / `Blocked`).
- **Safety Disclaimers:** Explicit banner reminding citizens that preparation does not equal government submission and no external authority has been automatically contacted.
- **Interactive Action Buttons:**
  - "Check Submission Readiness" (invokes readiness endpoint without mutating state).
  - "Prepare Government Submission" (formats and persists dispatch package).
  - Intentionally **omits** any false "Submit to Government" button.
