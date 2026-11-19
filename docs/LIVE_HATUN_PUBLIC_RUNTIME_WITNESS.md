# Hatun public runtime witness — bounded operator observation

Status: SOURCE-ONLY DIAGNOSTIC. Owner: szl-holdings/hatun-mcp.
Source baseline: 1cec84742e07c151a34c329ae2fb50dd5f87c7ab.
No hosted deployment, model inference, payment, secret handling or automation.

## Verified public problem

Hatun's admitted runtime is https://mcp.a-11-oy.com, not the product
page at https://a-11-oy.com/wires. On 2026-11-19:

| Surface | Public observation |
| --- | --- |
| GET /healthz | HTTP 200 (liveness only) |
| GET /readyz | HTTP 503; authentication UNAVAILABLE |
| GET /api/build-info | source 97bcf6b49ab7dcd78aaeae79a4a690e631f54836 (older than main) |
| anonymous HEAD /mcp/ | HTTP 402 (public payment challenge/interception) |

Previous observations included a 403 for the anonymous MCP HEAD.
Neither 402 nor 403 demonstrates an authenticated tool call, an approved
operator binding or successful x402 settlement.

The package's actual server_http.py::readyz deliberately requires a verified
receipt chain, configured signer and http_auth_configured() before reporting
ready. Do not bypass its guard or generate a substitute operator identity.

Kimi, accessed through Ollama on BETTERWITHAGE, proposed a bounded read-only
witness. Its recommendation to read healthz.build_revision was independently
corrected against the actual source: the deployed revision is in the separate
GET /api/build-info endpoint under build.revision. The source owner verified
that prior proposed operator-scope tests already existed and did not
duplicate them.

## Command: one bounded run, no scheduling

From the exact Hatun checkout, use a new private output path:

    python tools/live_hatun_public_runtime_witness.py --expected-source 1cec84742e07c151a34c329ae2fb50dd5f87c7ab --out C:\private-evidence\hatun-public-new.json

Four fixed public requests only: GET /healthz, GET /readyz,
GET /api/build-info, HEAD /mcp/. No redirects, environment proxy forwarding,
tokens, HTTP POST, retries, private signing keys, model requests or GPU jobs.
Each request has a 6-second timeout, bounded 64-KiB response body and strict
JSON parsing when JSON is expected. Only non-secret summary fields enter
the create-only unsigned SHA-256 integrity receipt.

Exit 2 / HOLD is mandatory, even when all public indicators report healthy:
no unauthenticated probe can prove an authorized operator's MCP initialize,
tools/list and allowlisted read-only tools/call, independently trusted
ECDSA-P256 DSSE signatures, tenant policy, code-signing trust, provider
settlement or production SLOs. A source SHA comparison is not an immutable
container signature.

## Protected operational admission

1. The deployment owner pins the current protected GitHub main, reviews
   source-to-runtime drift and uses its authorized, signed image workflow.
   Never silently rewrite the live service or resurrect the retired HF
   publisher.
2. The secret manager owner supplies an ALREADY admitted binding described
   in docs/HTTP_AUTHENTICATION.md. Do not print API keys, their fingerprints,
   or signing private-key material in terminal history, issues, Ollama or
   ChatGPT. A new binding requires an independently authorized procedure.
3. Independent public signer root approval and a fresh DSSE payload/signature
   verification are required. The signer key ID is only a label. See
   docs/DSSE_KEY_INJECTION.md. Do not trust whichever key the server advertises
   without an externally approved fingerprint/rotation record.
4. The protected operator harness must prove authenticated stateless /mcp/
   initialize, tools/list, one allowlisted read-only call, and denial of
   mutations. Preserve signed, source-bound, sanitized receipts.
5. Verify /readyz HTTP 200 with configured authentication, verified chain and
   configured signer, then sustained health, privacy, rollback and on-call.
   Only separately budgeted, model-qualified work can activate GPU training.

## Reproduction tests

    python -m unittest discover -s tests -p test_live_hatun_public_runtime_witness.py -v

Hermetic tests cover malformed and duplicate JSON, nonfinite values, request
method/path allowlists, redirect refusal, byte limits, Boolean type confusion,
source drift, unauthenticated 401/403, x402 402 interception, 200 fail-open,
503 readiness and create-only SHA receipt. The tests do not touch the
production provider or confer any authority.

This code is an independently reviewed adaptation of Kimi's proposal, not
a Kimi-executed patch or an automated production repair.
