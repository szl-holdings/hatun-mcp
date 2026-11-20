# Memory Court — day 2: middleware fail-closed specification (v0)

Status: **ROADMAP** (specification only; no middleware implementation in this PR). Co-authored in the three-brain holding-hands session (Kimi session-14, transcript receipted; GLM CTO lane). Continues docs/memory-court/MEMORY_COURT_DAY1.md (merged via #203).

## Pipeline

`operator-auth -> tenant bind -> 2026-07-28 profile normalization -> adjudication pre-check -> dispatch -> receipt assembly -> DSSE sign -> khipu append`

**Receipt semantics:** `none` means no receipt object is emitted. `abstention` is committed only after DSSE signing and khipu append. `signed-uncommitted` is internal evidence of a failed commit, never a success receipt. Dispatch stages dependent writes; the khipu commit releases them, and every failure aborts or quarantines them.

## Fail-closed decision table

| Failure point | HTTP/status outcome | Receipt kind emitted | Dependent writes stop? |
|---|---|---|---|
| Unauthenticated caller | `401 operator_auth_failed` | `none` | Yes; stop before tenant bind and dispatch. |
| Wrong tenant | `403 tenant_mismatch` | `none`; do not leak a cross-tenant receipt | Yes; forbid all staged writes. |
| Unknown signer key | `503 signer_key_unknown` | `none` | Yes; abort staged writes; no DSSE or khipu commit. |
| Trust-root version unknown | `503 trust_root_version_unknown` | `none` | Yes; stop before dispatch. |
| Dirty/unknown build | `503 build_not_admissible` | `none` | Yes; stop before dispatch. |
| Adjudication abstain | `200 adjudication_abstained`; not an allow | `abstention` after DSSE and khipu; otherwise the applicable `503` row | Yes for domain writes; only the audit receipt append may proceed. |
| Khipu write failure | `503 receipt_commit_failed` | `signed-uncommitted` internally; no committed receipt | Yes; roll back staged writes and never return success. |
| Signer unavailable | `503 signer_unavailable` | `none` | Yes; abort staged writes; no khipu append. |
| Malformed routing headers | `400 malformed_routing_headers` | `none` | Yes; stop before tenant bind and dispatch. |
| Restart mid-commit | `503 commit_outcome_unknown` if a response is possible; otherwise transport interruption | `none` until recovery; return only an original receipt found in khipu | Yes; quarantine staged writes and reconcile by request/idempotency ID without blind re-dispatch. |

**Recovery rule:** an existing khipu entry is the sole success proof for an interrupted request. Absence of an entry means abort, not inferred success.

## Test kit (day-2 scaffold)

Idiom decision: `pytest.mark.skip(reason=...)` — these are unexecutable ROADMAP skeletons, not executed known-failure tests (`xfail(strict=True)` would assert a failure mode we have not built and can drift); the decorator is removed when the middleware and the `day2` harness land.

`tests/memory_court/test_middleware_fail_closed.py` encodes the eight vectors above against a `day2.invoke(vector)` harness returning `status`, `receipt_kind`, `committed_receipt`, and `dependent_writes`.

## CI-red risks (checked against this PR)

1. New tests are module-skipped, so pytest collection/exit codes are unaffected.
2. Docs only elsewhere; no workflow, dependency, or config file changes.
3. No secrets, tokens, keys, or speculative numbers appear (gitleaks / Doctrine Overclaim Guard safe).
4. No new tool schema digests are asserted; the day-1 pin table remains authoritative until implementation.

## Labels

ROADMAP until the middleware slice lands and these tests are unskipped and green on record. Nothing here claims conformance to the MCP 2026-07-28 profile; the normative document pin remains day-1's open task.
