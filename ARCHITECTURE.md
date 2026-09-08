# Architecture — hatun-mcp

> Doctrine v11 LOCKED · Λ = **Conjecture 1** · SLSA L1 honest · L2 roadmap.
> *hatun* (Quechua) = "big / great". `receipts.in ≡ receipts.out`.

`hatun-mcp` is the **one signed Model Context Protocol (MCP) endpoint** that aggregates
the SZL backend services — the **a11oy** command platform (with its immune, companion,
and llm-router organs) plus **killinchu** (drones & vessels) — under PURIQ governance,
and re-exposes their tools to any MCP client.

It is a real, operational server built on the official `mcp` Python SDK
(`mcp.server.fastmcp.FastMCP`), with Streamable HTTP + SSE transports.

## The PURIQ governance pipeline

Every tool call flows through:

1. **Authenticate** — SZL API key → `client_id`; anonymous calls are declined.
2. **Yuyay-13 gate** on the input (input-as-data; OWASP MCP06 injection defense).
3. **Reputation** factor `Hatun_MCP(client) ∈ [0,1]`.
4. **2-person Yuyay gate** for state-changing tools (e.g. `killinchu_cue`, `halt_drone`).
5. **Call the real organ backend** within a latency budget.
6. **Mint a Khipu receipt** on success *and* failure (append-only sha256 DAG).
7. **Return a DSSE-signed response** — the client receives the receipt hash.

## Repository layout

```
hatun-mcp/
├── hatun_mcp/                       Server package (FastMCP app, gates, tools).
├── clients/                         Example MCP client integrations.
├── examples/                        Runnable examples.
├── tests/                           Self-tests (incl. static tool-count assertion).
├── Dockerfile                       Independently buildable container image.
├── docs/HATUN_SURFACE_CONTRACT.md    Canonical runtime/product lifecycle boundary.
├── PUBKEY_szlholdings-ec-p256.pem   PUBLIC cosign key (verification only).
├── renovate.json                    Dependency update config.
└── requirements.txt
```

## Tools exposed

**26 static tools** registered at import (verifiable: `tools/list` returns 26 with
`HATUN_MCP_DISABLE_DYNAMIC=true`), including 20 `szl_*` tools plus six governance
tools. The `szl_*` group includes the public GitHub estate observer and
drone/doctrine/anatomy tools. Additional tools may register dynamically when the
backends are reachable.

## GitHub observer trust boundary

`szl_github_estate_snapshot({})` passes through the existing authenticated
governance wrapper, then `backends.github_estate_snapshot` performs bounded GETs
against fixed `https://api.github.com` paths for public `szl-holdings` resources.
The dedicated client has no authorization header, inherited environment proxy,
redirect following, arbitrary target, retries, background workers, or write
operation. Repository metadata is normalized; provider bodies and transport
exception text are never forwarded as error messages.

The call has independent time/request/page/record/response-byte limits and
cancels unfinished child work at its deadline. Open PRs are tied to validated
repository and base/head identities; each check run must match the queried
head. No check runs and unknown check conclusions remain unassessed, not green.
Search/update races and pagination overflow are reported as evidence gaps.

Byte accounting bounds accepted application response-body data, not underlying
wire traffic. A shared exhaustion latch stops queued requests and further body
acceptance across concurrent observations. Transport prefetch and delivered but
rejected chunks are explicitly unmeasured. Successful-response citation hashes
still cover the exact complete body bytes used for that observation.

The observer computes SHA-256 over UTF-8 JSON with sorted keys, compact
separators, `ensure_ascii=False`, and `allow_nan=False`, excluding only the
top-level `evidence` member. The wrapper independently recomputes that digest
before adding it to the Khipu receipt detail covered by DSSE. Contract mismatch
discards the data and emits a sanitized failure receipt. The observer never
claims to sign; the existing envelope separately reports a real configured
P-256 signer or unsigned `PLACEHOLDER` mode. Existing optional receipt-sink
forwarding is unchanged and is distinct from GitHub access.

`COMPLETE` is scope coverage, not health, merge admission, or a whole-estate
attestation. The response explicitly excludes private data, default-branch SHA
resolution, legacy statuses, reviews/protection, deployments, and training.
Multi-request observations are not atomic. The public tool is not a substitute
for an authenticated administrative audit or a fresh exact-head merge check.

## Keys & secrets

The committed `PUBKEY_*.pem` is a **public** verification key only. Private signing keys
are never committed (enforced by `.gitignore` and the gitleaks gate).

## CI and publication

CI, SBOM, secret/image scanning, overclaim and pin checks are separate evidence
layers. Required checks and branch rules must be refreshed from GitHub before
publication; this document does not assert that a workflow's existence makes
it a required merge gate. Local tests are not hosted checks or a merge receipt.

Public product: [Hatun Gateway](https://a-11-oy.com/wires). The standalone HF
publisher is retired. Deployment of this package's `/mcp/` endpoint requires a
separate admitted operator; see the [surface contract](docs/HATUN_SURFACE_CONTRACT.md).

---

© 2026 Lutar, Stephen P. — SZL Holdings · Apache-2.0
