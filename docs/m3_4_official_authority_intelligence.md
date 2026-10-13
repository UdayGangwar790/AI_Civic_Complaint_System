# M3.4 — Authority Resolution: Current Contract and Limitations

## Current operational status

CVKI does **not** currently connect to a live official road-authority registry. The active default is `NoConfiguredAuthorityProvider`. Consequently, the default `/api/v1/authority/resolve` endpoint returns `authority_status: "not_verified"`, null authority parties, and empty evidence and source lists. It does not infer ownership from a city, road name, or coordinates.

An older static provider class and its sample records remain in the code for legacy/test compatibility. Those records are not independently verified official registry data; the class is not the active provider and must not be presented as a live or verified source. The domain allowlist only screens source URLs; passing the allowlist does not itself prove that a source or an authority claim is true.

## Provider and verification contract

The `AuthoritySourceProvider` interface supports a location and returns an `OfficialAuthorityLookup` or no result. A future provider may be used only when it supplies current, traceable evidence from an authoritative source. Provider errors and timeouts are surfaced by complaint draft/guidance and case-creation endpoints as HTTP 502 and 504 responses, respectively; they are not converted into a successful verified result.

Resolution states retain these meanings:

| Status | Meaning |
| --- | --- |
| `verified` | Valid evidence supports both road ownership and maintenance responsibility. |
| `partially_verified` | Valid evidence supports some authority information, but does not establish all required roles. |
| `not_verified` | No supported authority claim can be made. |

Road owner, maintenance authority, and builder/contractor are separate roles. A source must support the specific role assigned to it; a road owner is not automatically copied into the maintenance-authority field. Builder or contractor information is not inferred from a road name.

The API retains `evidence`, `limitations`, `sources`, `resolved_at`, and a human-readable `resolution_message` in its response. The default provider returns no authority source records. Never fabricate a source URL, retrieval timestamp, evidence statement, government contact, or portal.

## Client trust boundary

Draft, guidance, and case-creation requests may carry an authority object for compatibility, but the server ignores the submitted claims and resolves authority from the location using its configured provider. With the current default, these operations remain unverified and do not recommend an authority or official portal based on client-supplied content.

Government guidance is informational only. CVKI does not file, transmit, or submit a complaint to an external government service; `external_submission_status` remains `not_submitted`.

## Endpoint

`GET /api/v1/authority/resolve` accepts optional road, area, city, state, country, latitude, and longitude context. A successful HTTP response does not imply that an authority was verified: clients must inspect `authority_status` and the returned evidence/source records.

## Tests

`backend/tests/test_authority_m34.py` and `backend/tests/test_authority_api.py` cover the safe default, unverified behavior, source policy, and injected-provider contract. Complaint API and case API tests verify that client-supplied verified and partially verified claims are ignored. Provider-injection tests are controlled contract tests; they are not evidence of a live registry integration.
