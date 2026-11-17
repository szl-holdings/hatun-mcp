# Owned Cortex proposals through Hatun

The independent Python gateway exposes `szl_owned_cortex_infer` to an explicitly
bound operator key. The local console supplies a same-origin client for this
tool. This repository change does not establish a running remote gateway or
deployment on the public `a-11-oy.com/wires` product.

## Operation and authority

The request contains only `prompt` (1–4000 characters), `max_new_tokens`
(16–128, default 64), and `k` (1–4, default 3). Prompt whitespace is normalized
as in the Cortex request model. Unknown fields and coercible boolean/string
integers are rejected. The tool has no caller-selected URL, model, evidence
payload, credential, signing operation, or execution option.

An existing operator key must resolve through the gateway's explicit scope
binding. It then passes the existing Yuyay gate and receipt-chain check before
any upstream request. The tool is an explicit operator-only HTTP capability;
the x402 read-tool allowlist and its default paid capabilities are unchanged.
Payment-only credentials cannot invoke it. Caller approval/sovereign headers
remain untrusted. See [HTTP operator admission](HTTP_AUTHENTICATION.md).

The adapter reads the fixed owned origin's contract and submits at most one
inference request:

- `https://szlholdings-a11oy.hf.space/api/v2/governed-contract`
- `https://szlholdings-a11oy.hf.space/api/v2/governed-infer`

There are no redirects, fallback providers, automatic retries, inherited proxy
configuration, or forwarded operator/payment credentials. A 45-second total
deadline covers both requests, with a 5-second connect timeout, a 32 KiB
contract limit, and a 256 KiB inference-response limit. JSON must be UTF-8,
finite and free of duplicate keys. Local cancellation stops waiting; it cannot
guarantee cancellation of already-started upstream compute.

This is the owned Khipu GGUF Python Cortex. The product-domain
`a-11-oy.com/api/v2/*` is a distinct Cloudflare Worker with a different model,
response and receipt contract. The generic Hatun `llm_chat` gateway is also a
different protocol. Neither is used as an implicit fallback.

## Evidence returned

The normal Hatun response still includes `tool`, `status`, `data`,
`backend`, `khipu_receipt`, `dsse` and `governance`. Its `data` has schema
`szl.hatun.owned-cortex-proposal/v1`:

| Field | Meaning |
|---|---|
| `state` | `PROPOSAL`, `UNAVAILABLE`, or `REJECTED`; no action approval |
| `observed_at` | Gateway observation time |
| `source_revision` | Full upstream revision accepted from the request's contract preflight, when available |
| `phase` | `REQUEST_VALIDATION`, `CONTRACT_PREFLIGHT`, or `INFERENCE` |
| `upstream_http_status`, `last_http_endpoint` | Status and endpoint of the observed response; absent when no such response is available |
| `verification` | Structural scope, no signature verification, trace state and process-local Anatomy delivery scope |
| `upstream` | Accepted Cortex response, a bounded recognized error, or null |
| `reason_codes` | Fixed gateway failure codes |

For a proposal, the adapter checks the pinned model identity, source consistency,
request identity, output hash, public evidence handles and digest, citations,
modeled claims, receipt payload/digest and three Nemo ALLOW stages. It checks the
locked set of eight formulas, F1's replay-only application, and Lambda's
Conjecture 1 advisory status. Both response and receipt must retain
`NO_ACTION_AUTHORITY`, `executed: false`, and `tool_execution: false`.
Unknown nested fields are rejected before egress.

The accepted successful Cortex response is preserved, including the receipt
payload, digest and status. A trace sidecar may be `OBSERVED`, `UNAVAILABLE`, or absent;
the gateway reports that distinction. A valid UNAVAILABLE trace does not erase
a completed proposal. Malformed or inconsistent evidence is unavailable and
is not returned as a proposal. Known Nemo denials remain negative evidence.
Unrecognized provider error text is omitted while its observed HTTP status is
retained; dynamic exception suffixes are stripped.

The upstream receipt remains `UNSIGNED_RUNTIME` and
`EPHEMERAL_PROCESS_MEMORY_ONLY`. Its trace remains an unsigned response sidecar,
with collector delivery unverified. Anatomy delivery means the owned Cortex's
process-local observation, not an independently deployed 3D renderer or durable
store. The gateway's separately configured DSSE envelope can bind the gateway
observation digest; it does not turn the upstream receipt into a signature.
Raw prompt/output text is not copied into the gateway receipt detail.

`REQUEST_PREFLIGHT_BOUND` means the response agrees with the contract fetched
for this request and uses no-store/uncached transport metadata. It is not proof
of the newest GitHub deployment, cryptographic freshness, replay resistance,
model quality, independent Lean proof execution, or permission for a
consequential action. The source explicitly sets
`latest_deployment_verified: false` and
`signature_verification: NOT_PERFORMED`.

## Verification and source contracts

The offline fixtures derive from
[a11oy 4f06ec36](https://github.com/szl-holdings/a11oy/blob/4f06ec36c6af629c16b537b7bc9b92269e595658/a11oy_governed_cortex.py),
[its trace sidecar](https://github.com/szl-holdings/a11oy/blob/4f06ec36c6af629c16b537b7bc9b92269e595658/vsp_otel/trace_ir.py),
[its public BrainIndex metadata](https://github.com/szl-holdings/a11oy/blob/4f06ec36c6af629c16b537b7bc9b92269e595658/szl_brain_api.py),
and [pinned Nemo](https://github.com/szl-holdings/szl-nemo/tree/810231a531188bb569e3faa17396386eb0a5e260).
They use independently serialized hashes and do not invoke an actual model.

Run `python -m pytest -q tests/test_owned_cortex.py tests/test_http_admission.py
tests/test_http_payment_admission.py` with dynamic probing disabled. The tests
cover source/model/output/receipt mismatches, authority promotion, field
smuggling, malformed/oversized transport, timeouts, negative evidence,
operator-versus-payment admission, and request privacy. The Dockerfile
explicitly copies the adapter into the independent package image.

A live operational claim still requires an admitted runtime's exact source
identity, authenticated tool listing and one controlled proposal witness.
No production inference, key provisioning, deployment, signing configuration,
or receipt-storage change is performed by this source integration.
