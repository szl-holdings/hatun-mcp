# Owned Cortex proposal console

The existing Hatun Python console now includes an explicit operator proposal form.
It calls the same-origin `/mcp/` transport and the single reviewed
`szl_owned_cortex_infer` capability. Loading the page only reads process state;
a proposal requires the operator to submit the form.

## End-to-end boundary

The path is console → authenticated Hatun transport → governed tool wrapper →
fixed owned Cortex contract preflight → one inference request → validated
proposal/evidence → Hatun receipt → console display.

The product route `https://a-11-oy.com/wires` and this package's independently
deployed console are distinct surfaces. This change does not deploy either one.
It does not recreate the retired standalone Hugging Face publisher. See
[the surface contract](HATUN_SURFACE_CONTRACT.md) and
[HTTP admission](HTTP_AUTHENTICATION.md).

The form uses the existing family design and inline document, so it needs no
new runtime route, asset host, font, framework, or Docker copy. Public registry
and process panels retain their existing read behavior.

## What a request does

1. Accept a question of up to 4,000 characters and an existing admitted operator
   API key. The original input is length-checked, then normalized with the same
   surrounding-whitespace rules as the Python adapter; the visible question is updated
   before sending. The model budget is fixed at 64 tokens and three evidence handles.
2. Clear the credential field before the first network request. Keep the
   credential only in the current operation's memory, and send it as a header
   to the fixed same-origin MCP route. Do not put it in a URL, model argument,
   console log, cookie, local storage, or session storage.
3. Initialize the repository's supported MCP protocol, send the initialized
   notification, and call the named tool once. Reject a different server identity
   or negotiated protocol before tool dispatch. Do not retry automatically.
4. Stop accepting the response after 60 seconds or 1 MiB. Reject redirects,
   non-JSON responses, invalid UTF-8, wrong RPC identities, and malformed envelopes.
5. Check proposal-only authority, consistent source and request identities, and
   recompute SHA-256 of the submitted question and returned output in the browser.
   These checks are integrity/consistency checks, not trusted-signature verification.
6. Show the model output as literal text beside source/model identities, evidence
   count, Cortex receipt, Hatun receipt, and separately qualified observation states.

The form is disabled in insecure and embedded contexts. It uses no remembered
credential. Editing the question or credential clears the preceding answer and
evidence. Clear and page navigation discard local form/result state. Stop waiting
aborts the browser request and ignores late responses; it does **not** assert that
the upstream computation stopped. Cancellation never sends a retry.

## Evidence labels

| Field | Meaning |
|---|---|
| Proposal | Model output for human review; `executed=false`, `NO_ACTION_AUTHORITY` |
| Source | Revision reported by the fixed upstream and matched by Hatun's request preflight |
| Prompt/output digests | Recomputed in the browser to detect a mismatched question or output |
| Locked formulas | Eight locked source formulas; this client does not replay Lean proofs |
| Cortex receipt | Unsigned, ephemeral runtime receipt; not durable signing evidence |
| Hatun signature | Presence or absence in the returned envelope; verification not performed here |
| Trace observation | Upstream-reported observation if returned; absence stays explicit |
| Anatomy observation | Upstream-reported delivery/persistence; not independent remote delivery proof |
| Observation time | The individual request's observation time; not a current health guarantee |

A successful transport response, a receipt hash, and a reported signature are
different facts. The UI never combines them into a generic verified or ready badge.
No output is displayed after a contract mismatch or upstream refusal.

## Validation

`node --test tests/test_owned_cortex_console.mjs` executes the actual shipped
proposal client with a deterministic DOM/transport harness. It checks success and
negative cases including identity substitution, output/prompt digest mismatch,
authority upgrades, credential confinement, malformed/oversize responses, failed
admission, cancellation/deadline races, stale-result clearing, and plain-text
rendering. These provider responses are **SIMULATED**.

The native browser check exercises the Python ASGI MCP transport and Chromium
with a simulated fixed upstream and a temporary test-only operator binding.
Its evidence does not establish a live model invocation, trusted signing key,
production deployment, or public product readiness.

To reproduce the opt-in browser suite on Windows with installed Chromium-based Edge:

```powershell
$env:HATUN_RUN_BROWSER_TESTS = '1'
$env:HATUN_BROWSER_CHANNEL = 'msedge'
python -X utf8 -m pytest tests/test_owned_cortex_console_browser.py -q -s
```

For bundled Chromium, install Playwright and its browser and omit the channel
setting. An explicitly opted-in run must fail if its browser cannot launch.

The established console-state tests and the backend/admission regressions remain
required. The Node client suite runs in the existing hermetic CI step.

## Historical live canary

A separate [unsigned observation record](evidence/owned-cortex-canary-20261117.json)
records one request from the final adapter to the real fixed owned Cortex at
2026-11-17 00:14 UTC. It returned a structurally validated proposal with source,
model, output, evidence, receipt and trace bindings. That call used a synthetic
public question and did not initialize the Hatun signer or production operator
authentication. It establishes neither a deployed Hatun console nor current
availability, durable delivery, trusted signatures, proof replay or model quality.
The complete generated output is not included; its digest is recorded.

## Design references and decisions

These sources informed the integration; no upstream framework or SDK was vendored.

- [Palantir OSDK React](https://www.palantir.com/docs/foundry/ontology-sdk-react-applications/osdk-react)
  and [OSDK source](https://github.com/palantir/osdk-ts): keep an explicit contract
  between the model/data layer and the interface. This package keeps its existing
  implementation rather than assuming it has a Foundry Ontology.
- [Palantir action submission criteria](https://www.palantir.com/docs/foundry/action-types/submission-criteria):
  enforce admission at the server at invocation time. Catalog visibility and
  frontend controls do not grant permission.
- [Palantir action logs](https://www.palantir.com/docs/foundry/action-types/action-log):
  distinguish an observed event from complete history. Here, receipt and observer
  fields retain their declared scope and persistence limits.
- [Palantir AIP Evals](https://www.palantir.com/docs/foundry/aip-evals/overview):
  bind evaluation to specific inputs, outputs, and versions. The integration tests
  assert observable outcomes and failures, not a model's self-assessment.
- [NVIDIA NeMo Guardrails execution model](https://docs.nvidia.com/nemo/guardrails/latest/about-nemo-guardrails-library/how-it-works):
  preserve distinct input, retrieval, and output boundaries. SZL's `szl-nemo`
  package remains its own package; this is not a claim that NVIDIA's enterprise
  microservice is deployed.
- [LangGraph workflow design](https://docs.langchain.com/oss/javascript/langgraph/thinking-in-langgraph):
  keep steps and failure behavior explicit. The console sends one bounded request
  and avoids automatic retry of an operation that may already have produced a receipt.
- [τ-bench](https://arxiv.org/abs/2406.12045): an apparently correct final answer can
  still violate policy. Authority and admission are tested separately from output.
- [AgentDojo](https://arxiv.org/abs/2406.13352): treat returned model/tool text as
  untrusted data. The console renders it literally and cannot execute proposed actions.
- [GraphRAG paper](https://arxiv.org/abs/2404.16130) and
  [repository](https://github.com/microsoft/graphrag): graph retrieval patterns are
  useful research, but a summary graph is not an authorization or proof boundary.
  This change preserves the existing Second Brain path and adds no parallel index.

Official video metadata/descriptions were reviewed for Palantir's
[OSDK developer introduction](https://www.youtube.com/watch?v=vSJ5H00V7Es) and
[AIP Evals: Feedback to Fix](https://www.youtube.com/watch?v=hXSx9uG0R4k).
Full transcripts were not available in this review; technical decisions above are
supported by the linked documentation, source code, and papers.

Doctrine v11 LOCKED remains unchanged. Λ remains Conjecture 1, Khipu BFT safety
remains Conjecture 2, and no new mathematical proof, autonomous action authority,
or unique research result is claimed.
