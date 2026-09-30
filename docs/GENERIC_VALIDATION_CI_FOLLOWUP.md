# Generic validation: negative-test isolation follow-up

## 1. Authority and preserved source

This appends to the generic validation repair at signed commit
`def5293a37325e68d07b016a51371dd43ee28299`, based on
`482edd750f3354569ed417a5f443c43a1271ac91`. That commit and its prior evidence
remain intact. The user authorized replacing the negative test's real backend
boundary, testing it in verified offline isolation, then opening a signed draft
and observing ordinary source-reviewed CI. No merge or default-branch write is
authorized here.

## 2. Revalidated gap

`test_state_changing_tool_blocks_without_second_approver` previously relied on
the approval gate alone to close the real backend coroutine before execution.
A gate regression could therefore dispatch the backend during this negative
test. The intended result remains `declined` with `two_person_gate_required`.

## 3. Narrow change

The test now replaces `server.B.killinchu_cue` with an inert async fixture. Its
body calls a `Mock` that raises immediately on dispatch. The test also asserts
that the spy was never called, before retaining both existing denial assertions.
The wrapper still constructs a coroutine before evaluating approval; construction
does not execute the async fixture body. No application or operational behavior,
authentication configuration, permission or workflow guard is changed.

## 4. Offline execution receipt

The exact staged test function and six allowlisted definitions from the unchanged
server source ran in the Windows sandbox with a cleared child environment,
Python `-I -B`, a 30-second watchdog, and file/process/socket/DNS/environment
denials installed before candidate execution. Seven self-probes passed, including
the native socket and DNS audit events independently of the socket monkeypatches.

| Case | Expected assertion failure | Observed spy dispatches | Result |
| --- | --- | --- | --- |
| Actual approval gate | No | 0 | Passed |
| Synthetic dispatch followed by a matching denial response | Yes | 1, to the failing fixture only | Detected |
| Synthetic wrong denial reason without dispatch | Yes | 0 | Detected |

No blocked attempt occurred during candidate execution. Actual backend imports,
provider calls, key reads and operational dispatches were zero. Receipt hashes:

- `server.py`: `02d47bc7ecffb98ec88646775b2b00a8524a5c5e2acb1ca5a7b7f865c54e412b`
- `test_governance.py`: `80f4e39f7a1aac18a43c3441bea29d83a22c7385c10298ffbc461855bc3bac8b`

The first runner self-probe stopped before candidate execution because the
stdlib DNS codec attempted a lazy file import under the file-denial guard.
Preloading that stdlib codec before installing guards resolved the harness
setup issue; no guard was removed or weakened. The successful receipt and
reviewed runner are retained alongside the earlier local evidence.

## 5. CI effects and corrected credential classification

The existing ECDSA fixture generates disposable test material, places its PEM
temporarily in the process environment, and restores that state after the test.
Its backend and ledger forwarder are stubbed. It neither provisions persistent
access/trust nor writes or uploads private bytes in the visible source path.
Reference cleanup is not secure memory erasure. The user explicitly confirmed
that this fixture is within synthetic-test authority. This supersedes the
historical key-generation hold in section 7 of `GENERIC_VALIDATION_REPAIR.md`.

Source-reviewed PR effects comprise dependency/tool downloads, local container
build/start and localhost probes, security scans, GitHub SARIF/artifact/cache
uploads, and StepSecurity runner monitoring. Normal CI uses job-scoped GitHub
authorization for those uploads; application credentials are not mapped into
the test job. The application-provider-looking tests use mock transports,
synthetic data, inert descriptors or local computations. This follow-up closes
the identified negative cue test gap. Known local formula cases do not enter
the remote fallback; no receipt sink is supplied by the reviewed workflow.
There is no source-visible operational dispatch on the reviewed PR paths.

Main-only GHCR publication and scheduled drift/attestation jobs are not PR
effects. No workflow guard was changed. Transitive downloaded binaries and
ambient runner configuration were not exhaustively audited; this source review
does not certify network isolation of the entire hosted CI environment.

## 6. Prior evidence and limits

The preserved generic fixture receipt is 19 tests / 73 subtests passing, compared
with 59 failing assertions and four uncaught exceptions on the pinned baseline.
This follow-up adds one exact-test-function execution and two mutation controls.
It uses inert governance dependencies and an immediate coroutine driver, not a
full application import or local pytest integration run. Hosted CI results must
be reported separately for the final exact head. Neither static review nor these
fixtures establish runtime readiness or operational acceptance.

## 7. Delivery and remaining gaps

Prior evidence files and the original signed commit are preserved. The new
signed commit appends this receipt and the narrow test isolation change.
Credential-authority validation and the other original audit findings remain
outside this repair's completed scope. Operational and privacy-withheld code
remain unchanged.

Library delivery remains unconfirmed: the supported flow previously failed
first at network discovery and then with `Library prepare_uploads is not available`.
No saved-file IDs were returned and no alternate upload route was used. Local
patch/test/handoff artifacts and subsequent GitHub PR/check receipts provide
the available delivery evidence; they must not be described as Library saves.
