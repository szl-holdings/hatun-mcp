# Hatun generic validation repair

## 1. Authority and stack

Scoped source repair on `codex/hatun-fail-closed-validation`, based on
`szl-holdings/hatun-mcp@482edd750f3354569ed417a5f443c43a1271ac91`.
The input is `szl-estate-os` draft PR 55 at
`1422dc8a7898aa7f4c8c7b873439a4c58469b3c4`, specifically
`estate_reports/hatun_batch2/{report.md,evidence.json,files.csv}`.
GitHub remains canonical. No open Hatun PRs were observed at initial and final
preparation checks on 2026-09-30. The A11oy publisher owner retains that lane.
No merge, default-branch write, force push, security-setting change, key creation,
provider call, operational invocation, training or model loading is part of this repair.

## 2. Scope and evidence

Revalidated H2-CORE-002, H2-CORE-006 and H2-SURFACE-002 against the unchanged
audited source. The same unknown-mode readiness condition also exists in
`server_http.readyz`; the repair covers that generic route as well.

- `state.py`: normalize missing, malformed, unreadable and unknown signer modes
  to UNAVAILABLE; require literal boolean chain verification and ECDSA-P256 mode.
- `server_http.py`: use the same mode rule; return 503 for unknown modes,
  malformed chain results or verification exceptions, without exception text.
- `server.py`: require a dictionary with `deployed is True`, no non-null error,
  and either no HTTP status or a nonboolean integer in [200, 400). Preserve the
  adapters' existing treatment of 3xx. Non-dictionaries and backend exceptions
  become failure with a bounded error code. Failure receipts and reputation agree.
- `loop.py`: turn step/predicate exceptions and nonboolean predicate results into
  terminal errors with bounded reason codes; retain completed results and budgets.

The estate evidence-contract branch remains stricter and separate. Real receipt
signatures, credential validation and provider behavior are not exercised.

## 3. Coverage and explicit unknowns

This changes four generic production files, adds one synthetic test file, includes
it from the existing CI-enumerated console test module, and strengthens the
existing loop assertion to require the sanitized error label and absence of the
private marker. Existing CI gates and authentication configuration are unchanged.

Operational and privacy-withheld ranges from the pinned audit remain unmodified.
No operational function or provider adapter is executed. The test loader extracts
named generic AST definitions from actual source; it does not import server
startup, create keys or construct a real signer. This is not full-module, HTTP
transport, cryptographic, deployed-readiness or estate-wide coverage.

## 4. Findings and resulting behavior

Unknown signer modes previously produced READY when the chain was truthy. Both
surfaces now fail closed unless the observed mode is recognized and verification
returns literal True. The mode label alone still does not establish independent
signer identity, signature validity, authorization or external readiness.

Error-bearing backend dictionaries previously produced success when deployed
was true or absent. Those results now fail, including falsey but non-null errors,
unknown deployment and malformed HTTP status. Successful local/HTTP fixtures and
the separate COMPLETE/INCOMPLETE/UNAVAILABLE evidence branch retain their tested
behavior. Nested provider data is not validated by this generic envelope check.

Loop predicate exceptions previously escaped, and step exception messages were
returned. Both callbacks now produce terminal errors without raw exception text.
The loop still has no wall-clock deadline: this repair does not resolve
H2-CORE-005 or H2-SURFACE-003.

## 5. Per-file provenance

Original SHA-256 values independently match the pinned audit:

| Source | Original SHA-256 |
| --- | --- |
| state.py | `9545bee2349574061a8ffa873f07520c98891ac5582d7af0e421ffc56f42efc4` |
| server.py | `cca6664256c9939cca4aa1468c37707ba11165fd88d2192dd8717bfaefb271d7` |
| server_http.py | `5e6527551e0da449bdd429652c017a1e9a6135ac7b0f08060977d8f16563104c` |
| loop.py | `711467e8942688ebc613088dd849a4a65130cecd879aa89930afc5857aa58bf9` |

Local result receipts record revised source and test hashes. They describe
synthetic execution and are not signed operational receipts or runtime attestations.

## 6. Validation and proof limits

Python 3.12.12, pre-existing runtime, no installation: **19 tests, 73 subtests,
0 failures, 0 errors, 0 skips**. The identical tests on pinned source produced
**59 failing assertions and 4 uncaught exceptions**, confirming regression
sensitivity. Counts include subtest failures; they are not 63 separate defects.
`git diff --check` passes.

Execution used the Windows tool sandbox, a cleared child environment, `-I -B`,
a 30-second parent watchdog, immutable preloaded source bytes and Python audit,
socket, process and filesystem guards. Five harmless guard self-probes verified
denial before tests; the tests made zero blocked-access attempts. The runner uses
immediate synthetic coroutines that never suspend on I/O. This is a bounded
reviewed-source harness, not a general hostile-code sandbox certification.

The standalone test command for an appropriately isolated environment is:
`python -m unittest discover -s tests -p test_generic_validation.py -v`.
The task handoff includes the stricter local runner and before/after JSON receipts.

## 7. Remaining acceptance and next actions

PR creation is withheld because its automatic CI exceeds the task's execution
scope. `.github/workflows/ci.yml` installs dependencies, executes broad suites
and starts a container. In particular,
`tests/test_server.py::TestGithubEstateEnvelope::test_real_ephemeral_signature_binds_canonical_observation`
calls `ec.generate_private_key`; key creation is explicitly excluded from this
task. Other suites include the excluded operational context. No CI gate was
weakened or skipped to bypass this boundary. Hosted exact-head CI is NOT_RUN.

The current source permits a feature-branch push without matching any push
workflow; publication still requires a fresh trigger/ownership check. The owner
must resolve CI execution authority before creating the draft PR, then monitor
its exact-head checks to terminal. Merge remains the queue owner's task.

Credential authority (H2-SURFACE-001), receipt-prefix/mutability findings,
independent signer trust, deadlines, scientific-input bounds, schema/quorum
wiring and all remaining audit findings are open. There is no claim of full
estate readiness, runtime readiness, deployment, scientific validity or release.
