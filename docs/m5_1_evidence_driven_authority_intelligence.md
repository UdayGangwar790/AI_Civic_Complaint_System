# M5.1 — Evidence-Driven Authority Intelligence

## 1. Existing M3.4 behavior

M3.4 established the `AuthoritySourceProvider` interface, the `/api/v1/authority/resolve` response, official-source URL screening, and the states `verified`, `partially_verified`, and `not_verified`. It keeps road ownership, maintenance responsibility, and builder/contractor as separate roles. Complaint draft, guidance, and case-creation routes resolve authority on the server and ignore authority claims supplied by clients.

The active provider is `NoConfiguredAuthorityProvider`. CVKI does not currently connect to a live road or authority registry, so normal resolution returns `not_verified` with no authority parties or evidence. Road and administrative context can be reverse-geocoded through Nominatim; that context is not itself an official authority record. A legacy static provider remains inactive and is not evidence of a live integration.

## 2. M5.1 gap

Before M5.1, a generic accepted evidence item could accompany multiple authority claims without identifying which field it supported. The evidence response had no machine-readable field match or item-level verification explanation, and the citizen-facing panel showed claims without explaining their relationship to returned roles. Builder checks also accepted keyword-like provider text, while government-submission packaging had a separate weaker check based on a party source string or generic evidence text.

## 3. M5.1 changes

M5.1 extends the existing `AuthorityEvidence` model and resolver rather than adding another authority subsystem. Evidence items can identify the attribute they support, their resolver-assigned verification state, and a deterministic explanation. The existing `AuthorityResult` adds an optional citizen-facing explanation. Existing fields and the endpoint path are preserved.

Evidence source types must be in the approved source-type set, and supplied source URLs must pass the existing trusted-domain check. These are input-policy checks, not independent proof that a source is current or that its claims are true.

## 4. Evidence model

Each evidence item may contain:

- `source_name`, `source_type`, `reference`, `claim`, and `source_url` (existing provenance and claim fields)
- `matched_attribute`: `road`, `jurisdiction`, `road_owner`, `maintenance_authority`, or `builder_or_contractor`
- `verification_state`: `verified`, `partially_verified`, or `not_verified`, assigned by the resolver
- `explanation`: why that item did or did not support the identified field

An evidence item without a matched attribute remains visible as unlinked evidence but cannot verify an authority role. Provider-supplied verification state and explanation are not trusted; the resolver replaces them.

## 5. Verification states

- `verified`: a verified road/jurisdiction link exists and separate role-linked evidence supports both road ownership and maintenance responsibility.
- `partially_verified`: a verified road/jurisdiction link exists and role-linked evidence supports at least one, but not both, of road ownership and maintenance responsibility.
- `not_verified`: there is no verified road/jurisdiction link, no linked authority role, or no accepted evidence.

Evidence linked only to a road or jurisdiction establishes context, not responsibility. Evidence strength is represented by these evidence-coverage states. It is not a statistical probability, confidence score, or prediction accuracy estimate.

## 6. Ownership, maintenance, and builder distinctions

Road owner, maintenance authority, and builder/contractor remain distinct fields. A road owner does not imply the maintenance authority; either authority role does not imply a builder. A builder is returned only when there is a verified road/jurisdiction link and an item specifically matched to `builder_or_contractor` from an approved contract, tender, concession, or project-record source type. A party's free-text `source` label or unrelated mention of “builder” or “contractor” is insufficient. Government-submission packaging applies the same evidence requirement as a second check.

If this evidence is absent, `builder_or_contractor` is `null`; the related builder evidence item is marked `not_verified` when present. No contractor, contact, tender, project identifier, or source is inferred or generated.

## 7. Explainable evidence trail

`GET /api/v1/authority/resolve` returns the `evidence` list with its source claim, matched attribute, verification state, and explanation, plus `citizen_explanation` on the authority result. The citizen explanation is generated deterministically from the resolver's state and supported roles. It explains either that linked records support both roles, that only some roles are supported, or that the available records do not establish responsibility.

The existing authority panel displays that explanation and the evidence trail. It does not label an unlinked item as verified or convert a successful HTTP response into an authority decision.

## 8. Uncertainty and client trust

No percentage or machine-learning confidence is produced. A `not_verified` or `partially_verified` result remains visibly uncertain. Authority claims supplied in complaint draft, guidance, or case creation continue to be ignored in favor of server-side resolution. Authentication, ownership, and RBAC behavior are unchanged.

## 9. API changes

The authority endpoint and existing result fields are unchanged. Optional additive fields are:

- `AuthorityEvidence.matched_attribute`
- `AuthorityEvidence.verification_state`
- `AuthorityEvidence.explanation`
- `AuthorityResult.citizen_explanation`

The fields are optional to retain compatibility with stored cases and clients sending older authority payloads. Resolution results populate them when available.

## 10. Tests

Authority tests cover the safe default, verified and partial results, missing road linkage, role-specific evidence, rejection of unknown source types, resolver ownership of verification labels, deterministic citizen explanation, and builder rejection without linked contract/tender evidence. Existing complaint tests cover ignored client authority claims; complaint-case and authorization/ownership regression suites remain applicable. Government-submission tests cover the repeated builder check.

Provider-injection tests exercise controlled contracts. They are not live registry evidence or field validation.

## 11. Limitations

No live official road, ownership, maintenance, tender, or contractor registry is configured. A future provider must supply accurate, current source references and truthful field matches. The allowlist screens source types and URL domains but cannot independently validate source content, completeness, freshness, or jurisdiction boundaries. Standalone authority-resolution requests are not persisted as audit events; existing M4 audit logging covers other operational actions. The current tests do not measure real-world false-positive or false-negative rates.

## 12. Claims and validation

M5.1 is an engineering change that makes the evidence contract more explicit and applies stricter consistency checks. No scientific validation, comparative study, or novelty search was performed. CVKI should not be described as the “first,” novel, or guaranteed to identify the correct authority on this basis.

## 13. Future research

Potential follow-up work includes provider integrations with documented provenance and freshness, human adjudication of authority decisions, region-specific evaluation against independently verified road records, measurement of incorrect and unresolved assignments, and privacy-aware auditability for evidence changes. Such work should be scoped separately and report its data and validation limits.
