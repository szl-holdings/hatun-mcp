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
- `szl_yuyay_score`, `yuyay_gate_check`,
  `mesh_quorum_status`, `governance_pacbayes_bound`: local calculations and their
  ordinary audit receipts.
- `szl_formula_evaluate`: only exact names `puriq`, `sigmoid`, `liu_hui_pi`.
  Other names can fall back to a remote backend and are denied by this profile.
- `resources/read`: only `hatun://doctrine/locked-numbers`.

Protocol initialization, ping, cancellation notifications and catalog listing
remain available to admitted callers. Other methods, unknown/dynamic tools,
raw signing, arbitrary Khipu appends, caller-asserted PURIQ execution, external
actions and global recent-receipt reads are denied. In particular, a `write` or
`admin` binding does not enable them over HTTP. A real higher-privilege approval
protocol must be implemented and reviewed before expanding this profile.

`X-Second-Approver` and `X-Sovereign-Mode` are not verified authority and are
ignored. Public `/connect` and server-card metadata disclose the HTTP policy;
the full package catalog is not permission to invoke every tool over HTTP.
Trusted local stdio operation is separate and retains its existing behavior.

POST messages must be individual JSON-RPC 2.0 objects with JSON content type.
Batches are rejected; streamed bodies are bounded to 256 KiB and a 10-second
read deadline before dispatch. Oversize and slow requests return 413 and 408.
The SDK receives the same inspected bytes. Host and Origin protection remains
enabled under the existing deployment configuration.

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
