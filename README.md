[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Doctrine v11 LOCKED](https://img.shields.io/badge/Doctrine-v11_LOCKED-d4a444.svg)](https://github.com/szl-holdings/lutar-lean)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19944926.svg)](https://doi.org/10.5281/zenodo.19944926)
[![CI](https://github.com/szl-holdings/hatun-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/hatun-mcp/actions)
[![Security Policy](https://img.shields.io/badge/Security-Policy-red.svg)](SECURITY.md)

---
title: Hatun-MCP
emoji: 🪢
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Doctrine-aware MCP server with PURIQ governance
tags:
  - mcp
  - model-context-protocol
  - agentic
  - governance
  - szl-holdings
---

# Hatun-MCP — *the great context protocol*

**Hatun** (Quechua: *hatun* — "great / large / principal") is SZL Holdings'
doctrine-aware [Model Context Protocol](https://modelcontextprotocol.io) server.
It exposes every SZL flagship capability to external MCP clients — Claude Desktop,
Cursor, Continue, Zed, Goose, Replit, Sourcegraph Cody — while wrapping **every
single tool invocation** in the PURIQ governance pipeline:

- **Yuyay-13 gate** — a 13-axis content/intent check on every call; injection
  markers and below-floor intent are declined *before* any backend runs.
- **Khipu receipts** — every invocation (allowed *or* declined) is recorded on a
  sha256-linked hash chain. Receipts are verifiable via `szl_khipu_verify`.
- **DSSE-signed responses** — each tool result is signed with an ECDSA P-256 key
  (in-toto DSSE envelope). The public key is served at `/pubkey`.
- **Default decline** — anonymous calls (no SZL API key) are refused and receipted.
  No anonymous tool execution.
- **2-person Yuyay gate** — state-changing tools (e.g. target cue, OTA, control)
  require a second approver header. One key cannot act alone.

> Hatun-MCP is a **transport & discovery** organ. It does **not** decide — the
> Yuyay-13 heart decides; Hatun-MCP carries governed capability to the world's
> agents through the standard protocol.

## Endpoints

| Path | Purpose |
|------|---------|
| `POST /mcp` | Streamable HTTP transport (MCP 2025-06-18) — **recommended** |
| `GET /sse` | Legacy HTTP+SSE transport (message endpoint `/sse/messages/`) |
| `GET /.well-known/mcp/server-card.json` | Registry discovery card (16 tools) |
| `GET /healthz` | Liveness + chain-verified + signer mode |
| `GET /pubkey` | DSSE verification public key (PEM) |

**Hosted URL:** `https://szlholdings-hatun-mcp.hf.space`
**MCP (Streamable HTTP):** `https://szlholdings-hatun-mcp.hf.space/mcp`
**MCP (SSE):** `https://szlholdings-hatun-mcp.hf.space/sse`

## Authentication

All tool calls require an SZL API key:

```
Authorization: Bearer szl_...
```

Keys are provisioned by the SZL customer portal. Anonymous calls are declined and
receipted (see `authentication.required` in the server card).

## The 16 tools

| Tool | What it does | State-changing? |
|------|--------------|-----------------|
| `szl_a11oy_code_chat` | Chat with the a11oy.code unified open-LLM router | no |
| `szl_killinchu_detect` | Detect/identify a drone from RF / Remote-ID / ADS-B | no |
| `szl_killinchu_cue` | Signed BoE target cue | **yes — 2-person gate** |
| `szl_sentra_scan` | Sentra immune scan of code / SBOM / image | no |
| `szl_rosie_reason` | Rosie brain-jack reasoning | no |
| `szl_khipu_verify` | Verify a Khipu receipt hash + merkle proof | no |
| `szl_lean_verify` | Verify a Lean theorem on the lutar-lean kernel | no |
| `szl_puriq_evaluate` | Compute PURIQ P(x,t) + factor breakdown | no |
| `szl_yachay_dome_predict` | Yachay-Dome impact prediction for a track | no |
| `szl_wayra_recent` | Recent WAYRA ingestions (honest stub until WAYRA ships) | no |
| `szl_anatomy_3d_render` | Three.js scene snapshot URL for an organ | no |
| `szl_doctrine_lookup` | Semantic lookup across Doctrine v11/v12/v13 + thesis | no |
| `szl_yuyay_score` | 13-axis Yuyay breakdown of content | no |
| `szl_thesis_query` | RAG query against the thesis corpus | no |
| `szl_drone_lookup` | Canonical drone DB entry from killinchu | no |
| `szl_formula_evaluate` | Evaluate a doctrine formula primitive (PURIQ P(x,t), KL, sigmoid, Liu Hui π) | no |

## Connect from Claude Desktop

```json
{
  "mcpServers": {
    "hatun-mcp": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://szlholdings-hatun-mcp.hf.space/mcp",
               "--header", "Authorization: Bearer szl_YOUR_KEY"]
    }
  }
}
```

## Connect from Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "hatun-mcp": {
      "url": "https://szlholdings-hatun-mcp.hf.space/mcp",
      "headers": { "Authorization": "Bearer szl_YOUR_KEY" }
    }
  }
}
```

## Run locally

```bash
pip install -r requirements.txt
export HATUN_MCP_SIGNING_KEY_PATH=/path/to/ecdsa_p256_private.pem
export HATUN_MCP_ALLOWED_ORIGINS="http://localhost"
uvicorn hatun_mcp.server_http:app --host 0.0.0.0 --port 7860
```

## Security posture (OWASP MCP Top 10)

Hatun-MCP maps its controls to the OWASP MCP Top-10 (MCP01–MCP10): tool-poisoning
and prompt-injection are caught by the Yuyay-13 gate; excessive-agency and
unauthorized-state-change are caught by default-decline + the 2-person gate;
tamper-evidence comes from the Khipu hash chain and DSSE signatures. See
`HATUN_MCP_DOCTRINE.md` for the full mapping.

---

Built by **Yachay** for SZL Holdings. Protocol revision **2025-06-18**.
Doctrine v11 LOCKED numbers preserved. Apache-2.0.
