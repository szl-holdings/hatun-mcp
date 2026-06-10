[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Doctrine v11 LOCKED](https://img.shields.io/badge/Doctrine-v11_LOCKED-d4a444.svg)](https://github.com/szl-holdings/lutar-lean)
[![CI](https://github.com/szl-holdings/hatun-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/hatun-mcp/actions/workflows/ci.yml)
[![SLSA](https://img.shields.io/badge/SLSA-L1_honest_%C2%B7_L2_roadmap-22c55e.svg)](https://slsa.dev/spec/v1.0/levels)

<div align="center">

# 🪢 hatun-mcp

**The great context protocol** — *hatun* (Quechua) = "big / great".

The **one signed MCP endpoint** that aggregates the SZL backend services — the
**a11oy** command platform (and its policy, memory and operator capability services)
plus **killinchu** (drones & vessels) — under PURIQ governance and re-exposes their
tools to any MCP client.

[Hugging Face Space](https://huggingface.co/spaces/SZLHOLDINGS/hatun-mcp) ·
[GitHub Org](https://github.com/szl-holdings)

`receipts.in ≡ receipts.out`

</div>

---

## What this is

A **real, operational** Model Context Protocol server built on the official `mcp`
Python SDK (`mcp.server.fastmcp.FastMCP`). Every tool call is governed by the PURIQ
formula:

1. **Authenticate** the client (SZL API key → `client_id`); anonymous calls are declined.
2. **Yuyay-13 gate** on the input (input-as-data; OWASP MCP06 injection defense).
3. **Reputation** factor `Hatun_MCP(client) ∈ [0,1]`.
4. **2-person Yuyay gate** for state-changing tools (e.g. `killinchu_cue`, `halt_drone`).
5. Call the **real organ backend** within a latency budget.
6. Mint a **Khipu receipt** on success **and** failure (append-only sha256 DAG).
7. Return a **DSSE-signed** response — the client receives the **receipt hash**.

### Tools exposed

- **25 static tools** registered at import (verifiable: `tools/list` returns 25 with
  `HATUN_MCP_DISABLE_DYNAMIC=true`):
  - **19 `szl_*` tools** — `szl_a11oy_code_chat`, `szl_a11oy_operator_reason`, `szl_a11oy_sentinel_scan`,
    `szl_anatomy_3d_render`, `szl_doctrine_lookup`, `szl_drone_lookup`,
    `szl_formula_evaluate`, `szl_khipu_verify`, `szl_killinchu_cue`,
    `szl_killinchu_detect`, `szl_lean_verify`, `szl_puriq_evaluate`,
    `szl_rosie_reason`, `szl_sentra_scan`, `szl_thesis_query`, `szl_wayra_recent`,
    `szl_yachay_dome_predict`, `szl_yuyay_score`, and **`szl_lambda_quorum`** (Byzantine Λ verdict).
  - **6 governance tools** — `yuyay_gate_check`, `khipu_append_and_verify`,
    `dsse_sign`, `mesh_quorum_status`, `puriq_master_tool`, `governance_pacbayes_bound`.
- **Service-derived tools** registered *dynamically* at startup from each backend
  service's live catalog at `/api/<service>/v1/mcp/tools`, named `<service>_<tool>`. The
  dynamic count is **probe-dependent**: it equals 25 + (whatever the reachable services
  publish), and is 0 extra when dynamic registration is disabled or all services are
  unreachable.

> **Naming note.** Three backend services are addressed by **immutable internal route
> segments** that are kept verbatim because renaming them would break the live routes. The
> exact segment strings are published in the live OpenAPI document at `/openapi.json`; this
> README refers to each service only by its user-facing role: the **YACHAY** reasoning
> cortex (read-only memory), the **operator console**, and the **CHAPAQ** egress
> immune-inspector (policy/gates).

### Honest reachability (HONESTY OVER CHECKLIST)

| Backend service | Catalog route | Status 2026-06-03 |
|-----------------|---------------|-------------------|
| a11oy — **YACHAY** read-only reasoning cortex / memory | `/api/<yachay>/v1/mcp/tools` | **LIVE** — 4 tools |
| killinchu | `/api/killinchu/v1/mcp/tools` | **LIVE** — 4 tools (cue/halt_drone are 2-person) |
| a11oy — operator console | `/api/<operator>/v1/mcp/tools` | **LIVE** — 12 tools |
| a11oy — **CHAPAQ** egress immune-inspector (policy/gates) | `/api/<chapaq>/v1/gates` | **LIVE (gates-derived)** — 8 gates + 3 actions; this service does **not** expose a JSON `/v1/mcp/tools` catalog (SPA shell), so tools are derived from `/gates` |
| a11oy — command | `/api/a11oy/v1/mcp/tools` | **PAUSED (503)** — "ask a maintainer to restart it". Registers **zero** tools + one honest `a11oy_status` tool. **Requires a founder-flipped restart of the Space** before its ≤49 policy gates surface. **Self-heals** to a full live catalog on the next server restart once a11oy returns 200 — no code change, no fabricated stubs. |

### Byzantine quorum + BLS aggregate

`szl_lambda_quorum` fans a governance-critical Λ verdict out to the five backend services
and decides under a **Byzantine n ≥ 3f+1 quorum (n=5, f=1)**: ≥ 4 services must be reachable
and ≥ 3 must agree. Participating receipts are **BLS12-381 aggregated** (`py_ecc`;
honest sha256 Merkle-root fallback if the BLS backend is absent). With a11oy paused,
quorum degrades gracefully to the 4 live services (n=4 still satisfies n ≥ 3f+1) and
discloses the degradation in `governance.quorum`.

---

## Run locally (stdio)

```bash
pip install -r requirements.txt
python -m hatun_mcp.server          # stdio mode for Claude Desktop / Codex
```

## Run hosted (Streamable HTTP)

```bash
uvicorn hatun_mcp.server_http:app --host 0.0.0.0 --port 7860
# MCP endpoint:  http://127.0.0.1:7860/mcp   (legacy SSE at /sse)
```

The DSSE signing key is injected at runtime via the `HATUN_MCP_SIGNING_KEY` (PEM)
Space secret; without it the signer runs in honest `PLACEHOLDER` mode (clearly
labeled, never a fake signature).

---

## MCP client setup

### Claude Desktop
Drop `examples/claude-desktop-config.json` into
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) /
`%APPDATA%\Claude\claude_desktop_config.json` (Windows), replacing `szl_YOUR_KEY`:

```json
{
  "mcpServers": {
    "hatun-mcp": {
      "command": "npx",
      "args": ["-y", "mcp-remote",
        "https://szlholdings-hatun-mcp.hf.space/mcp",
        "--header", "Authorization: Bearer szl_YOUR_KEY"]
    }
  }
}
```

### Codex (`~/.codex/config.toml`)
```toml
[mcp_servers.hatun-mcp]
command = "npx"
args = ["-y", "mcp-remote", "https://szlholdings-hatun-mcp.hf.space/mcp",
        "--header", "Authorization: Bearer szl_YOUR_KEY"]
```

### Continue (`~/.continue/config.json`)
```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "stdio",
          "command": "npx",
          "args": ["-y", "mcp-remote",
            "https://szlholdings-hatun-mcp.hf.space/mcp",
            "--header", "Authorization: Bearer szl_YOUR_KEY"]
        }
      }
    ]
  }
}
```

---

## Tests

```bash
HATUN_MCP_DISABLE_DYNAMIC=true python -m pytest tests/ -q
# tests/test_server.py    — list tools, call a tool, assert response shape
# tests/test_quorum.py    — quorum math + threshold edge cases + BLS aggregate
# tests/test_adapters.py  — mocked organ endpoints, adapter wiring + honest gaps
# tests/test_governance.py— Khipu chain, Yuyay gate, PURIQ factor (pre-existing)
```

---

<sub>

**Doctrine v11 LOCKED — 749 / 14 / 163 · Λ = Conjecture 1 (NOT a theorem) · SLSA L1 honest · L2 verified-provenance on roadmap (L3 not claimed)**
`receipts.in ≡ receipts.out`

Signed-off-by: Yachay &lt;yachay@szlholdings.ai&gt;
Co-Authored-By: Perplexity Computer Agent &lt;agent@perplexity.ai&gt;

</sub>
