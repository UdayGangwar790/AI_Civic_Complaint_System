# M5.2 — Advanced Civic Intelligence

## 1. Objective

M5.2 adds deterministic post-submission decision support using persisted CVKI cases: issue recurrence, recent road/city reporting concentration, resolution-evidence state, a bounded recurrence contribution to the existing priority score, and explainable recommendations. It does not introduce a predictive ML model or automate government actions.

## 2. Existing M3/M4 capabilities

- **M3.1/M3.3:** Persisted cases, authenticated citizen history, and owner-only case detail.
- **M3.7:** Text, issue-category, distance, and short-window duplicate classification (`unique`, `possible_duplicate`, `duplicate`). This concerns whether reports may describe the same incident.
- **M3.8:** A bounded, explainable 0–100 engineering priority heuristic using issue, text, duplicate, location, and CV signals.
- **M3.9:** In-app notifications for case, duplicate, priority, and lifecycle events.
- **M4.4/M4.5:** Admin assignment, authority ownership checks, status transitions, notifications, and audit events.
- **M4.7:** Admin analytics, including all-time road/city case counts, distributions, and time series.
- **M4.8:** Admin audit log storage and access controls.
- **M5.1:** Evidence-linked authority information; M5.2 does not change its authority contract.

## 3. Gap analysis

Duplicate classification did not represent repeated issues over longer periods. The existing geographic concentration was all-time road/city counting without a recent time window, issue breakdown, or open-case count. Lifecycle status had no separate staff resolution note/state. Priority reasons were available, but priority did not use the newly computed recurrence signal, and possible-duplicate language described an ongoing recurring problem even when reports might refer to one incident.

## 4. Recurrence definition

A recurrence candidate must be a persisted, non-draft prior case with the same exact issue category, a prior timestamp inside the configured 180-day window, and a separation greater than the existing 72-hour duplicate window. When both cases have coordinates, their Haversine distance must be at most 250 m. If either coordinate pair is missing, the normalized road and city names must match exactly. Road/city fallback is not fuzzy geocoding.

`recurrence_count` counts qualifying previous cases, not the current case. A matching case within the duplicate time window does not count as recurrence. Different issue categories and distant locations do not count. Related references are returned to admins only; assigned authorities receive counts and explanations without other case IDs. The history scan examines at most the configured 5,000 most recent persisted cases; `history_scan_complete` and response limitations make a capped scan explicit.

### Duplicate vs. recurrence

- **Duplicate:** similar reports may describe the same real-world incident, using M3.7's short temporal window and semantic/spatial checks.
- **Recurrence:** separate same-category reports at the same location over time, outside that duplicate window. It indicates repeated reports, not proof of a recurring physical defect or shared cause.

## 5. Hotspot methodology

The existing all-time `geographic_concentration` response field remains unchanged. M4.7's admin analytics response adds `hotspots`, aggregated from persisted cases created in the previous 30 days. Road and city strings are normalized for case and surrounding whitespace before grouping. A group is returned only when it reaches the configured minimum of 3 reports. It includes report count, dominant issue category, unresolved count, time window, and a factual explanation. Ties in category frequency are deterministic.

Hotspots do not include exact coordinates, citizen IDs, complaint text, or case references. A hotspot is a reporting concentration, not proof of cause, risk, recurrence, or infrastructure failure. Case-level intelligence uses the bounded recent-case scan and states when that scan may be incomplete.

## 6. Resolution evidence states

The canonical M4.5 lifecycle and transitions are unchanged. An authorized admin or the authority assigned to the case may optionally submit a staff-authored resolution note when transitioning to `resolved`; the existing audit event records whether such a note was supplied, not the note text.

- `status_only`: case is not currently marked resolved/closed.
- `evidence_missing`: case is resolved/closed without a current resolution note.
- `evidence_supported`: an attributed staff note was recorded for the current resolution attempt.

`evidence_supported` means a note is stored, not that CVKI independently verified a repair. Reopening advances the evidence cutoff; old notes remain stored but do not support a later resolution state. M5.2 does not upload, store, or validate repair photos or external attachments.

## 7. Priority improvements

M3.8 base, text, duplicate, location, CV, and level thresholds remain unchanged. Server-side case creation supplies the persisted recurrence result to an internal scoring argument; clients cannot submit recurrence data to the priority endpoint. If recurrence is detected, it adds `min(5, 2 * recurrence_count)` points, reported as `recurrence_score` with a reason and evidence item. Total remains clamped to 0–100. This is an engineering heuristic, not a calibrated or scientifically validated weight.

Duplicate scoring remains separate. Reasons now explain that a possible duplicate may be the same incident and is not itself evidence of recurrence.

## 8. Recommendation logic

Admin and assigned-authority case intelligence may return recommendations when stored facts meet deterministic conditions:

- qualifying recurrence: consider inspecting the underlying road condition;
- at least 3 recent same-road/city reports: consider prioritizing field inspection;
- an open case at least 30 days old: consider reviewing assignment/status;
- a resolved/closed case without a current note: consider recording available inspection evidence.

Every recommendation contains its basis. It is advisory, not an instruction to an authority, a confirmed fact, or a government submission. No recommendation is produced from citizen identity, fabricated statistics, or unsupported contractor/authority information.

## 9. API changes

- `GET /api/v1/admin/cases/{reference_id}/intelligence`: admin-only recurrence, local concentration, resolution state, existing priority reasons, and recommendations. Related historical reference IDs may be included.
- `GET /api/v1/authority/cases/{reference_id}/intelligence`: authority-only and restricted to cases assigned to the authenticated authority; related case IDs are omitted.
- Existing `GET /api/v1/admin/analytics` adds optional `hotspots`; legacy `geographic_concentration` remains.
- Existing status PATCH requests accept optional `resolution_evidence` text only when transitioning to `resolved`.
- Complaint cases add optional `recurrence_analysis`, `resolution_evidence`, and `resolution_evidence_recorded_at` fields. Older stored records default safely.
- Priority responses add `recurrence_score`; priority request shape does not accept recurrence input.

No public citizen intelligence endpoint was added. Existing citizen case ownership endpoints and M5.1 authority payloads remain unchanged.

## 10. Authorization

Admin intelligence is guarded by existing `require_role(admin)`. Authority intelligence uses existing authority RBAC plus an explicit `assigned_to_user_id == current_user.user_id` check. Citizens cannot access either intelligence endpoint. Admin historical references are not returned to authorities. Existing authentication, complaint ownership, notifications, assignment, and audit behavior remain in force.

## 11. Tests

M5.2 tests cover no history, valid recurrence, issue/location/time separation, exact recurrence count, duplicate-vs-recurrence, resolution states, stale notes, recommendations, client-supplied recurrence rejection, admin/citizen/authority access, assignment isolation, and server-side recurrence-to-priority persistence. M4.7 hotspot tests cover minimum density, dominant category, unresolved count, rolling window, and sparse data. Existing duplicate, priority, lifecycle, authority/complaint, and ownership suites remain part of validation.

*Final test totals are recorded in the M5.2 task report after validation.*

## 12. Limitations

The recurrence distance/window and hotspot threshold are engineering defaults, not validated optima. Recurrence depends on exact issue labels and available coordinates or normalized road/city values. The per-case recurrence/concentration scan is capped at 5,000 recent cases. The analytics hotspot group is by road/city text rather than a geospatial centroid or causal cluster. Resolution notes are self-reported staff records and no repair media is stored or independently checked. Existing legacy duplicate/NLP inputs are outside this change's scope. No additional audit timeline or external integration is introduced.

## 13. Future research

Potential next work includes adjudicated recurrence labels, measuring duplicate/recurrence confusion, tuning thresholds on a documented representative dataset, geospatial clustering with privacy review, validated resolution-media provenance, and evaluating whether recommendations improve review workflows. These studies should report their sampling and error limits. M5.2 results do not establish scientific validity, emergency prediction, guaranteed repair verification, live government integration, or a “first-ever” claim.
