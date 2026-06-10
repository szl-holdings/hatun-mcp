# STATUS.md — hatun-mcp (MCP Server)

**Updated:** 2026-06-03
**Doctrine v11 — 749 / 14 / 163 — replay hash c7c0ba17**

---

## What's Live

- **MCP server** — real, operational Model Context Protocol server on the official
  `mcp` Python SDK (`FastMCP`). Streamable HTTP `/mcp` + legacy SSE `/sse` + stdio.
- **25 static tools** (19 `szl_*` incl. `szl_lambda_quorum` + 6 governance tools);
  verify with `HATUN_MCP_DISABLE_DYNAMIC=true python -m hatun_mcp.server` → `tools/list`
  returns 25. **Dynamic service-derived tools** are added at startup from each reachable
  service's catalog — the live total is probe-dependent (25 + reachable-service tools).
- **PURIQ governance per call** — Yuyay-13 gate, Khipu receipt (success AND failure),
  ECDSA-P256 DSSE envelope, reputation factor, 2-person gate for state-changing tools.
- **Byzantine quorum** (`szl_lambda_quorum`, n=5 / f=1) + **BLS12-381 aggregate** of
  participating organ receipts.
- **Organ adapters** — amaru (4), killinchu (4), rosie (12), sentra (8 gates + 3 actions),
  all wired live from `/api/<organ>/v1/...`.
- **CITATION.cff** — citable, ORCID 0009-0001-0110-4173.

## What's Experimental / Honest Gaps

- **a11oy** — HF Space is **PAUSED (503)**. Registers zero tools + one honest
  `a11oy_status` tool until a **founder restarts** the Space. Self-heals on next
  server restart once a11oy returns 200. The "49 a11oy gates" target is blocked on this.
- **sentra** — exposes no JSON `/v1/mcp/tools` catalog (SPA shell); tools are derived
  from `/api/sentra/v1/gates` + known action routes. Disclosed, not faked.
- **DSSE signer** — runs in honest `PLACEHOLDER` mode unless `HATUN_MCP_SIGNING_KEY`
  (PEM) is injected as a Space secret.
- **Sigstore Rekor** transparency-log inclusion remains a disclosed placeholder
  boundary (Doctrine v12 §2).

## Correction (this PR)

The previous README claimed hatun-mcp had **MOVED to `platform/services/hatun-mcp`** and
was archived. That was **stale/incorrect**: the repo is not archived, the merge target
does not exist (404), and this repo is the canonical, operational home. The README is
restored to reflect reality.

## What's Deprecated

Nothing deprecated in this repo.

---

*Co-Authored-By: Perplexity Computer Agent*
*Doctrine v11 — 749/14/163 — c7c0ba17*
