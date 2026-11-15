# llms-install.md

How an LLM agent or marketplace integrator installs and verifies **hatun-mcp**
(the great context protocol - one MCP endpoint aggregating the SZL backend
services under PURIQ governance, with Khipu receipts and DSSE signing).

## What you get

A Model Context Protocol server built on the official mcp Python SDK 2.x.
Every tool call is governed: authenticate, Yuyay-13 gate, reputation factor,
2-person gate for state-changing tools, real organ backend call within a
latency budget, Khipu receipt minted on success AND failure, DSSE-signed
response. Anonymous calls are declined.

## Prerequisites

- Python with pip
- Node.js / npx (only if you use the mcp-remote client bridge below)

## Option A - run locally (stdio, e.g. Claude Desktop / Codex)

    pip install -r requirements.txt
    python -m hatun_mcp.server

## Option B - run hosted (Streamable HTTP)

    uvicorn hatun_mcp.server_http:app --host 0.0.0.0 --port 7860

Endpoints on the hosted server:

- MCP endpoint: http://127.0.0.1:7860/mcp/
- Process liveness: http://127.0.0.1:7860/healthz
- Fail-closed readiness: http://127.0.0.1:7860/readyz

/readyz returns 200 only when the receipt chain verifies, a non-placeholder
signing key is active, and an operator scope binding is configured; otherwise
503 with the failing check named. Do not present a PLACEHOLDER-mode signer as
signed.

## Client configuration (SAMPLE - replace szl_YOUR_KEY with an admitted key)

Claude Desktop (claude_desktop_config.json):

    {
      "mcpServers": {
        "hatun-mcp": {
          "command": "npx",
          "args": ["-y", "mcp-remote",
            "http://127.0.0.1:7860/mcp/",
            "--header", "Authorization: Bearer szl_YOUR_KEY"]
        }
      }
    }

Codex (~/.codex/config.toml):

    [mcp_servers.hatun-mcp]
    command = "npx"
    args = ["-y", "mcp-remote", "http://127.0.0.1:7860/mcp/",
            "--header", "Authorization: Bearer szl_YOUR_KEY"]

Continue (~/.continue/config.json):

    {
      "experimental": {
        "modelContextProtocolServers": [
          {
            "transport": {
              "type": "stdio",
              "command": "npx",
              "args": ["-y", "mcp-remote",
                "http://127.0.0.1:7860/mcp/",
                "--header", "Authorization: Bearer szl_YOUR_KEY"]
            }
          }
        ]
      }
    }

For a remote deployment, substitute the admitted operator-provided HTTPS MCP
URL. The checked-in configs are SAMPLE and carry no credentials.

## Verify your install

    curl -i http://127.0.0.1:7860/healthz
    curl -i http://127.0.0.1:7860/readyz
    HATUN_MCP_DISABLE_DYNAMIC=true python -m pytest tests/ -q

Report healthz=200 as process liveness only. readyz=200 as local receipt-chain
and signer readiness only. Neither establishes upstream organ availability -
probe each backend route separately before labeling it LIVE (KANCHAY status
contract in the README).

## Logo

Marketplace logo: assets/logo-400.png (400x400 PNG).

## Honesty boundaries

- No fabricated metrics; receipts carry only what was actually observed.
- Sample configuration is never evidence of a deployed runtime.
- This file was added by the 2026-11-15 estate audit remediation campaign
  (szl-org-health #348); commands are taken verbatim from the README.
