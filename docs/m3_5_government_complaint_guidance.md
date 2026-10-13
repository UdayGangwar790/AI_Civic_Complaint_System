# M3.5 — Government Complaint Portal Guidance

## 1. Objective
The objective of Module M3.5 is to empower citizens with actionable, step-by-step guidance on where and how to submit civic grievances directly to official statutory portals.

"M3.5 provides guidance for citizen-initiated government complaint submission. It does not automatically submit complaints to government systems."

The system strictly avoids deceptive claims of automated filing, maintaining an unequivocal separation between creating a CVKI reference case and submitting an official complaint to a government agency.

---

## 2. Guidance Architecture & Generation Flow
The guidance engine operates downstream of M3.4 authority intelligence:
```
Citizen Detection & Location
       │
       ▼
M3.4 Authority Intelligence (Verified / Partially Verified / Not Verified)
       │
       ▼
M3.5 Guidance Engine (app/services/guidance.py)
       ├── Channel Recommendation (Official Portal, Municipal Office, etc.)
       ├── Official Portal Link (Subject to strict Allowlist)
       ├── Localized Step-by-Step Instructions
       ├── What to Attach Checklist
       ├── What to Write Prompt
       └── Explicit "not_submitted" Status
```

### Guidance Logic by Verification State:
1. **`verified`**: Recommends the specific statutory portal (e.g., CPGRAMS / NHAI portal for national highways, BBMP Sahaaya for Bengaluru municipal roads), attaching verified official links and targeted filing categories.
2. **`partially_verified`**: Recommends the identified agency while warning the citizen that secondary boundaries or contractor oversight remain unverified.
3. **`not_verified`**: Explicitly advises the citizen that authority could not be verified from official registry sources. Informs the user to contact the local municipal ward office or verify jurisdiction prior to filing. **Never guesses or invents an authority.**

---

## 3. Official Portal Policy & Anti-Fabrication Guarantees
- **No Fabricated URLs**: The guidance engine only provides portal URLs that are explicitly verified and sourced from the official authority source record or statutory registry.
- **Strict Domain Validation**: URLs must belong to `.gov.in`, `.nic.in`, `.gov`, or configured statutory domains. Any unverified URL is discarded.
- **Missing Portal Handling**: When no official portal link is verified, the guidance engine outputs `official_portal_url: null` and provides instructions for in-person municipal filing or phone helplines, without generating synthetic links.

---

## 4. Multilingual Citizen Guidance Support
Guidance text is localized into three language modes:
- **English (`en`)**: Formal, accessible administrative guidance.
- **Hindi (`hi`)**: Clear Devanagari script tailored for non-technical Hindi speakers.
- **Hinglish (`hinglish`)**: Conversational Romanized Hindi widely used in conversational citizen interfaces.

### Factual Information Immutability:
Translations are applied strictly to explanatory instructions and steps. Factual entities are never altered:
- Official department names (e.g., *"National Highways Authority of India (NHAI)"*, *"BBMP"*) remain verbatim.
- Official URLs (`https://pgportal.gov.in`) remain untouched.
- Case reference IDs and technical metadata remain unchanged.

---

## 5. Strict Separation: CVKI Case vs Government Case
CVKI reinforces the boundary between internal case tracking and external government filing across all layers:

| Dimension | CVKI Case | Government Complaint |
| :--- | :--- | :--- |
| **Creation** | Created and stored in CVKI MongoDB repository | Must be submitted manually by citizen on official portal |
| **Identifier** | `CVKI-YYYYMMDD-XXXXXX` | Government grievance docket number (obtained after filing) |
| **Status** | `submitted` (to CVKI) | `external_submission_status = "not_submitted"` |
| **UI Display** | Badge: *"CVKI Case: Submitted"* | Badge: *"Government Submission: Not Submitted"* |

The field `external_submission_status` remains strictly `"not_submitted"`. CVKI never manufactures fake government registration tokens or confirmation receipts.

---

## 6. Safety & Non-Automated Boundaries
In compliance with project safety constraints, M3.5 deliberately does **NOT**:
- Perform automated login to government websites
- Solve or bypass CAPTCHAs
- Intercept or process OTPs
- Store citizen government credentials or passwords
- Scrape private or credential-gated portals
- Send automated form payloads to external endpoints

---

## 7. API Specification
### Endpoint:
`POST /api/v1/complaint/guidance`

**Request Body:**
```json
{
  "issue": "pothole",
  "road": "NH 44",
  "area": "Electronic City",
  "city": "Bengaluru",
  "authority_status": "verified",
  "road_owner": "Ministry of Road Transport and Highways (MoRTH)",
  "maintenance_authority": "National Highways Authority of India (NHAI)",
  "official_portal_url": "https://pgportal.gov.in",
  "language": "hinglish"
}
```

**Response Body (`GovernmentGuidanceResponse`):**
```json
{
  "recommended_channel": "CPGRAMS / NHAI Official Grievance Portal",
  "authority_basis": "Verified statutory jurisdiction under National Highways Authority of India (NHAI).",
  "official_portal_url": "https://pgportal.gov.in",
  "official_source": "NHAI National Highway Gazette & Toll Information System",
  "external_submission_status": "not_submitted",
  "steps": [
    "Official portal https://pgportal.gov.in open kijiye.",
    "Road Transport and Highways ya NHAI category select kijiye.",
    "Verified location enter kijiye: Electronic City, Bengaluru.",
    "Pothole ki original photo attach kijiye.",
    "CVKI dwara generate kiya gaya draft paste ya verify karke submit kijiye.",
    "Submit karne ke baad mila hua government reference number note kijiye."
  ],
  "what_to_attach": [
    "Road issue ki saaf tasveer (Clear photo)",
    "GPS location coordinates ya landmark address",
    "CVKI generated complaint description"
  ],
  "what_to_write": "Complaint draft me road ka naam, landmark aur pothole ki gambhirta jarur likhein.",
  "limitations": [
    "CVKI automatically government portal par submit nahi karta hai.",
    "Submission citizen dwara official portal par manually complete kiya jana chahiye."
  ]
}
```

Guidance is also attached to `POST /api/v1/complaint/draft` responses and embedded in case follow-up metadata for authenticated citizen case tracking.

---

## 8. Frontend Integration
The frontend citizen interface reflects M3.5 guidance across two key workflows:
1. **Interactive Complaint Workflow (`App.jsx`)**:
   - Renders a prominent **Official Complaint Submission Guidance** card below the complaint draft.
   - Displays clear status badges: `CVKI Case: Submitted to CVKI` vs `Government Submission: Not Submitted`.
   - Links directly to verified government portals using safe `target="_blank" rel="noopener noreferrer"` attributes.
   - Step-by-step numbered instructions, checklist for attachments, and prompt suggestions.
   - Warning banner when authority status is `not_verified`.
2. **Citizen Complaint History Modal (`CaseDetailModal`)**:
   - Displays guidance records saved alongside persistent CVKI cases.
   - Shows external filing status alongside the verified authority breakdown.

---

## 9. Testing & Quality Assurance
The module is covered by 15 dedicated unit and API tests (`backend/tests/test_guidance_m35.py`):
1. Verified authority guidance generation
2. Partially verified authority guidance with warnings
3. Not verified authority with no guessed authorities
4. Official portal source presence
5. Handling when no official portal is available
6. Discarding untrusted / unverified portal URLs
7. Enforcement that `external_submission_status` is `"not_submitted"`
8. English language step generation
9. Hindi language step generation
10. Hinglish language step generation
11. Preservation of official names across all languages
12. Preservation of URLs across all languages
13. Automatic attachment of guidance to `/api/v1/complaint/draft`
14. Guidance API endpoint (`/api/v1/complaint/guidance`) validation
15. Distinction between CVKI case creation and external government submission
