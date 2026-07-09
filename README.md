[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Doctrine v11 LOCKED](https://img.shields.io/badge/Doctrine-v11_LOCKED-d4a444.svg)](https://github.com/szl-holdings/lutar-lean)
[![CI](https://github.com/szl-holdings/hatun-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/hatun-mcp/actions/workflows/ci.yml)
[![SLSA](https://img.shields.io/badge/SLSA-L1_honest_%C2%B7_L2_roadmap-22c55e.svg)](https://slsa.dev/spec/v1.0/levels)

<div align="center">

# 🪢 hatun-mcp

**The great context protocol** — *hatun* (Quechua) = "big / great".

The **one signed MCP endpoint** that aggregates the SZL backend services — the
**a11oy** command platform (and its live immune, companion and llm-router organs)
plus **killinchu** (drones & vessels) — under PURIQ governance and re-exposes their
tools to any MCP client.

[Hugging Face Space](https://huggingface.co/spaces/SZLHOLDINGS/hatun-mcp) ·
[GitHub Org](https://github.com/szl-holdings) ·
[LLM Router](https://github.com/szl-holdings/szl-router)

</div>

> **📦 Canonical MCP server (Wave D consolidation).** This standalone repository is the
> **canonical, live** doctrine-aware MCP server — the fleet's only spec-compliant Streamable
> HTTP MCP transport, carrying the full governed tool catalog and the `hf-deploy` workflow that
> ships the running server. The monorepo copy at
> [`platform/packages/hatun-mcp`](https://github.com/szl-holdings/platform/tree/main/packages/hatun-mcp)
> is a **non-canonical embedded copy** (it carries `CANONICAL.md` pointing here) that exposes a
> smaller tool set for local imports and must not diverge from this server's contracts. Folding
> the platform copy in is a later founder step; repos are **not deleted** here. Λ = **Conjecture
> 1** (advisory) is preserved verbatim.

<div align="center">

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
    `szl_companion_reason`, `szl_immune_scan`, `szl_thesis_query`, `szl_wayra_recent`,
    `szl_yachay_dome_predict`, `szl_yuyay_score`, and **`szl_lambda_quorum`** (Byzantine Λ verdict).
    > Two tools were **renamed 2026-06-16** to honest organ names —
    > `szl_immune_scan` (was the retired codename scan tool) and
    > `szl_companion_reason` (was the retired codename reason tool). See
    > [`DEPRECATED.md`](DEPRECATED.md) for the old→new mapping. The old names are
    > **not** served (they are not registered in `tools/list`).
  - **6 governance tools** — `yuyay_gate_check`, `khipu_append_and_verify`,
    `dsse_sign`, `mesh_quorum_status`, `puriq_master_tool`, `governance_pacbayes_bound`.
- **Service-derived tools** registered *dynamically* at startup from each backend
  service's live catalog at `/api/<service>/v1/mcp/tools`, named `<service>_<tool>`. The
  dynamic count is **probe-dependent**: it equals 25 + (whatever the reachable services
  publish), and is 0 extra when dynamic registration is disabled or all services are
  unreachable.

> **Naming note.** The three previously-codenamed backends were **purged**; their
> capabilities are now served directly by the **live honest a11oy organs** on
> `a-11-oy.com`: the **immune** organ (egress policy/gates inspector — *Hukulla*),
> the **companion** organ (operator / reasoning console), and the **llm** organ
> (open-LLM tier router). Hatun-MCP addresses them by these honest role names; the
> live routes are published in `/openapi.json`.

### Honest reachability (HONESTY OVER CHECKLIST)

| Backend organ | Catalog route | Status 2026-06-16 |
|-----------------|---------------|-------------------|
| a11oy — **llm** open-LLM tier router | `GET /api/a11oy/v1/llm/tiers` | **LIVE (200)** — `llm_tiers` derived from the live tier catalog |
| killinchu | `/api/killinchu/v1/mcp/tools` | **LIVE** — 4 tools (cue/halt_drone are 2-person) |
| a11oy — **companion** operator / reasoning console | `/api/a11oy/v1/companion/{ask,act,recommend}` | **LIVE (200)** — 3 tools derived from live action routes (no JSON `/v1/mcp/tools` catalog) |
| a11oy — **immune** (Hukulla) egress policy inspector | `GET /api/a11oy/v1/immune/gates` | **LIVE (200, gates-derived)** — gates + `screen`/`verdict`; the immune *screen* is the signed `/immune/verdict` route (there is no separate `/screen`) |
| a11oy — command / flagship | `/api/a11oy/v1/mcp/tools` | Registers a11oy-flagship tools when the JSON catalog is exposed, else one honest `a11oy_status` tool. **Self-heals** on the next server restart once the catalog returns 200 — no code change, no fabricated stubs. |

> **Purge note (2026-06-16).** The three previously-codenamed backends were purged
> (their old routes now 404). Hatun-MCP was repointed to the **live honest a11oy
> twins** above and verified 200 before wiring. No tool is ever pointed at a 404;
> where a sub-route does not exist (e.g. `/immune/screen`) the tool maps to the
> closest real route (`/immune/verdict`) and the mapping is disclosed in the
> adapter docstring and the catalog `reason`.

### Byzantine quorum + BLS aggregate

`szl_lambda_quorum` fans a governance-critical Λ verdict out to the five backend services
and decides under a **Byzantine n ≥ 3f+1 quorum (n=5, f=1)**: ≥ 4 services must be reachable
and ≥ 3 must agree. Participating receipts are **BLS12-381 aggregated** (`py_ecc`;
honest sha256 Merkle-root fallback if the BLS backend is absent). If any organ's
policy route is not live, quorum degrades gracefully (n=4 still satisfies n ≥ 3f+1)
and discloses the degradation in `governance.quorum`.

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
        "https://szlholdings-hatun-mcp.hf.space/mcp/",
        "--header", "Authorization: Bearer szl_YOUR_KEY"]
    }
  }
}
```

### Codex (`~/.codex/config.toml`)
```toml
[mcp_servers.hatun-mcp]
command = "npx"
args = ["-y", "mcp-remote", "https://szlholdings-hatun-mcp.hf.space/mcp/",
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
            "https://szlholdings-hatun-mcp.hf.space/mcp/",
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

## The Ouroboros loop (doctrine cross-reference)

hatun-mcp does **not** implement the estate's Ouroboros bounded-recursion kernel itself; its
PURIQ orchestrator is a **bounded, single-pass per-tool-call flow**, not recursion. This
section is a **doctrine cross-reference** plus an honest note on how that flow embodies the
loop's receipt-closed identity (`receipts.in ≡ receipts.out`, already carried in this README).

The canonical definition is the receipt-closed kernel
[`szl-holdings/ouroboros` → `src/loop-kernel.ts`](https://github.com/szl-holdings/ouroboros/blob/main/src/loop-kernel.ts) (`runLoop`): *bounded recursion with measurable convergence* that MUST terminate on one
of four exit conditions — `converged | consistent | aborted | budgetExhausted` — and emits a
governance receipt for every run. **The trace is the product.**

How hatun-mcp embodies that primitive (in `hatun_mcp/puriq.py`):

- **Bounded & terminating.** Each tool call is a finite pipeline — Yuyay-13 gate → mesh
  quorum (Byzantine n ≥ 3f+1) → HUKLLA tripwire → Khipu append → DSSE-sign → compose the
  master-formula scalar — that always terminates within a latency budget and returns a
  receipt hash. There is no unbounded loop.
- **Receipt-closed.** Every call mints a Khipu link on an append-only sha256 DAG and the
  client receives the **receipt hash**. That is this repo's live realization of the header
  identity `receipts.in ≡ receipts.out` — a **metaphor (doctrine, not math)**, where each
  signed receipt is fed back into the DAG as an auditable input.

**Honesty (Doctrine v11 · 749/14/163):** Λ is consumed here as an input scalar in [0,1] and
is **Conjecture 1** — advisory, *never* a proven theorem. This is a *bounded, terminating*
governance flow — it makes **no** perpetual-motion or zero-cost claim.

---

<sub>

**Doctrine v11 LOCKED — 749 / 14 / 163 · Λ = Conjecture 1 (NOT a theorem) · SLSA L1 honest · L2 verified-provenance on roadmap (L3 not claimed)**
`receipts.in ≡ receipts.out`

Signed-off-by: Yachay &lt;yachay@szlholdings.ai&gt;
Co-Authored-By: Perplexity Computer Agent &lt;agent@perplexity.ai&gt;

</sub>
