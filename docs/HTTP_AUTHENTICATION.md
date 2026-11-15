# HTTP operator admission

The Python package's HTTP transports require an existing, explicitly admitted
operator key. A `szl_` prefix is not authentication. This package has no live
customer-portal validation or introspection integration, and does not claim one.
The independent package's deployment authority remains in
[the surface contract](HATUN_SURFACE_CONTRACT.md).

## Configure an existing operator identity

The supported startup/runtime binding is `HATUN_MCP_SCOPE_<fingerprint>`, with
an exact value of `read`, `write`, or `admin`. The fingerprint is the first 16
lowercase hexadecimal characters of PBKDF2-HMAC-SHA256 over the UTF-8 key,
using `HATUN_MCP_FP_SALT` (default `hatun-mcp/api-key-fingerprint/v1`) and
`HATUN_MCP_FP_ITERATIONS` (default `210000`). Existing correctly provisioned
bindings retain their names. Changing those KDF settings requires the operator
to update the corresponding bindings.

Compute the binding in the operator's protected environment from an already
authorized key. Never place the key in source, command-line arguments, logs,
URLs, or a response. This procedure does not authorize issuing keys or copying
credentials between services. The accepted key is 5–256 ASCII characters,
starting with `szl_`, followed only by letters, digits, `_` or `-`.

Missing, empty and unrecognized bindings reject the request. Removing a binding
revokes it on the next request in that process. Bindings in another process must
be updated through its own deployment/configuration mechanism. There is no
implicit demo or anonymous HTTP identity, including when
`HATUN_MCP_ALLOW_ANON=true` is set for local package behavior.

Send exactly one credential source: `Authorization: Bearer <key>` or
`X-Api-Key: <key>`. Duplicate or simultaneous credential headers are rejected.
Admission covers `/mcp`, `/sse` and `/messages`, including their child paths,
before any SDK dispatch. Denials do not execute a tool or mint a receipt.
Only stateless Streamable HTTP at `/mcp/` is enabled. After key admission,
legacy SSE and message endpoints return `410 legacy_transport_disabled`;
their session context cannot safely inherit independently authenticated message
identities. No legacy SDK session is mounted. `/connect` and the root descriptor
report `sse_endpoint: null`.

## Read-only HTTP profile

Every admitted scope is limited to the same explicit HTTP capability set:

- `szl_github_estate_snapshot`: bounded public GitHub reads.
- `szl_yuyay_score`: local scoring with a receipt attributed to the admitted
  operator identity.
- `szl_formula_evaluate`: only exact names `puriq`, `sigmoid`, `liu_hui_pi`.
  Other names can fall back to a remote backend and are denied by this profile.
- `resources/read`: only `hatun://doctrine/locked-numbers`.

Protocol initialization, ping, cancellation notifications and catalog listing
remain available to admitted callers. Other methods, unknown/dynamic tools,
raw signing, arbitrary Khipu appends, caller-asserted PURIQ execution, external
actions and global recent-receipt reads are denied. In particular, a `write` or
`admin` binding does not enable them over HTTP. A real higher-privilege approval
protocol must be implemented and reviewed before expanding this profile.
Direct governance calculators (`yuyay_gate_check`, `mesh_quorum_status`, and
`governance_pacbayes_bound`) are also denied: their existing receipt path uses
the fixed identity `mcp`, so it cannot audit which HTTP operator invoked them.

`X-Second-Approver` and `X-Sovereign-Mode` are not verified authority and are
ignored. Public `/connect` and server-card metadata disclose the HTTP policy;
the full package catalog is not permission to invoke every tool over HTTP.
Trusted local stdio operation is separate and retains its existing behavior.

POST messages must be individual JSON-RPC 2.0 objects with JSON content type.
Batches are rejected; streamed bodies are bounded to 256 KiB and a 10-second
read deadline before dispatch. Oversize and slow requests return 413 and 408.
The SDK receives the same inspected bytes. Host and Origin protection remains
enabled under the existing deployment configuration.

## x402 payment admission (Cloudflare Monetization Gateway)

Payment admission is off by default. When it is off, a `PAYMENT-CONTEXT` header
is never parsed or trusted, and an operator key is still required. To turn it
on, set these variables before process start. Invalid values fail startup.

| Variable | Value |
|---|---|
| `HATUN_MCP_X402_SCHEME` | `upto` (recommended for MCP) or `exact`. Unset or `off` disables admission. |
| `HATUN_MCP_X402_AMOUNT_ATOMIC` | The gateway rule's price in atomic USDC units (1 unit = $0.000001), from 1000 to 100000000. For `upto`, this is the rule's authorised maximum. |
| `HATUN_MCP_X402_PAID_TOOLS` | Optional. A comma-separated subset of the three HTTP read tools. Default: all three. |
| `HATUN_MCP_X402_LEEWAY_SECONDS` | Optional clock leeway from 0 to 30. Default: 5. |
| `HATUN_MCP_PUBLIC_BASE` | The public HTTPS origin the gateway charges, for example `https://mcp.a-11-oy.com`. The audience is exactly `<PUBLIC_BASE>/mcp/`. A loopback base refuses every real token and logs `x402_audience_not_public`. |

How a request is admitted:

- Only requests to exactly `/mcp/` may carry `PAYMENT-CONTEXT`. Any other
  transport path returns `403 payment_context_not_accepted_for_path`. Health,
  discovery and `/api/*` routes never read the header and stay free.
- Send exactly one credential: an operator key or one `PAYMENT-CONTEXT`. A
  request with both, or with two contexts, gets `401 ambiguous_credentials`. A
  request with neither is unpaid and gets
  `401 payment_or_operator_key_required`.
- [`hatun_mcp/payment_context.py`](../hatun_mcp/payment_context.py) checks the
  JOSE header before it retrieves any key. `alg` must be `EdDSA`, and a
  token-supplied `jku`, `jwk`, `x5u` or `x5c`, `crit` or `b64` is refused. The
  Ed25519 key comes only from the pinned JWKS at
  `https://payments.cloudflare.com/certs`. That retrieval follows no redirects,
  inherits no environment proxies, and is bounded to 5 seconds and 64 KiB. Keys
  are cached for the time the `Cache-Control` header allows, corrected by `Age`
  and `Date` and capped at 24 hours. Expired keys are never used, even if the
  refetch fails. An unknown `kid` forces at most one refetch per 60 seconds.
  `aud` must equal the audience string exactly, and `scheme` and `amount` must
  equal the configured terms, so a payment made under a cheaper rule is refused.
  `iat`, `nbf` and `exp` must be integers inside the leeway.
- An invalid context gets `403 payment_context_invalid` with a reason code such
  as `EXPIRED`, `WRONG_AUDIENCE`, `BAD_SIGNATURE` or `WRONG_AMOUNT`. If no fresh
  key set can be obtained, the request gets
  `503 payment_verification_unavailable` (fail closed). Neither response runs a
  tool or mints a receipt.
- A valid context admits the identity `x402:<first 16 hex of SHA-256(token)>`
  with scope `read`, on the same read-only HTTP profile described above. Write,
  admin and dynamic tools stay denied. The receipt detail records the
  payment's public facts: scheme, authorised amount, audience, `kid`,
  `iat`/`nbf`/`exp` and the token's SHA-256, with `settlement_evidence: false`.
  The raw token is never stored, logged or echoed.

How settlement is reported:

- `upto`: `PAYMENT-SETTLEMENT: {"amount":"<AMOUNT_ATOMIC>"}` is set only when
  the request was a single `tools/call` of a paid tool and its governed result
  was `success`. Every other response below 400 reports `{"amount":"0"}`, which
  settles nothing. That covers `initialize`, notifications, `tools/list`,
  `resources/read`, unpaid tools, and declined or failed calls. A response of 400
  or above carries no header. A downstream `PAYMENT-SETTLEMENT` or
  `PAYMENT-RESPONSE` is dropped.
- `exact`: no `PAYMENT-SETTLEMENT` is set, because the gateway settles the
  signed amount for every matching request. An MCP session sends `initialize`,
  `notifications/initialized`, `tools/list` and `tools/call` as separate POSTs,
  so an `exact` rule on `/mcp/*` charges each one. Use `upto` for MCP.

What this does not prove:

- A verified context is not evidence of settlement, of who paid, or that the
  request is unique. The documented claims carry no nonce or `jti`, and
  identical authorisations are identical tokens, so no replay cache is kept.
- Cloudflare does not document whether an `exact` payment settles when the
  origin answers 400 or above, or what an `upto` 2xx without the header
  settles. This origin always sets the header on `upto` 2xx and 3xx responses.
- The live tokens' `alg`, `kid` and the JWKS `Cache-Control` were not observed
  from the build environment, which cannot reach the JWKS host. Before claiming
  the paid path works, run one controlled paid canary and record the receipt.
- A caller that bypasses the gateway, for example through a User-Agent
  exemption in an edge rule, reaches this origin without a context and is
  refused.

## Readiness and deployment evidence

Public discovery, health, key and console-state routes remain readable without
credentials. They do not validate a caller's key. `/readyz` requires a verified
local receipt chain, a usable ECDSA-P256 signer and at least one recognized
operator binding. Console HTTP readiness includes the same authentication
configuration requirement. A binding's presence proves configuration, not that
the correct operator possesses the key or that any remote organ is available.

Before admitting a deployment, separately verify the exact build revision,
trusted signer identity, rejected forged/absent credentials and a successful
permitted read call using the existing admitted key. Do not use a signing or
state-changing tool as an availability probe. Keep the retired standalone
publisher retired and do not substitute another service's MCP identity.
