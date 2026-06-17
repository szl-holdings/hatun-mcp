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
├── Dockerfile                       Container image (HF Space deploy target).
├── push_to_hf.py                    Sync to the SZLHOLDINGS/hatun-mcp HF Space.
├── PUBKEY_szlholdings-ec-p256.pem   PUBLIC cosign key (verification only).
├── renovate.json                    Dependency update config.
└── requirements.txt
```

## Tools exposed

**25 static tools** registered at import (verifiable: `tools/list` returns 25 with
`HATUN_MCP_DISABLE_DYNAMIC=true`), including 19 `szl_*` organ tools plus
drone/doctrine/anatomy tools. Additional tools may register dynamically when the
backends are reachable.

## Keys & secrets

The committed `PUBKEY_*.pem` is a **public** verification key only. Private signing keys
are never committed (enforced by `.gitignore` and the gitleaks gate).

## CI gates (required on `main`)

`sbom` is the required merge gate. `ci`, `gitleaks`, `trivy`, overclaim, and pin-check
also run.

Public surface: [SZLHOLDINGS/hatun-mcp on Hugging Face](https://huggingface.co/spaces/SZLHOLDINGS/hatun-mcp).

---

© 2026 Lutar, Stephen P. — SZL Holdings · Apache-2.0
