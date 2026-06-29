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
- **Organ adapters** — llm (tiers), killinchu (4), companion (ask/act/recommend),
  immune (gates + screen/verdict), all wired live from the a-11-oy.com routes
  (`/api/a11oy/v1/{immune,companion,llm}/...`).
- **CITATION.cff** — citable, ORCID 0009-0001-0110-4173.

## What's Experimental / Honest Gaps

- **immune** — there is no separate `/api/a11oy/v1/immune/screen` route (404); the
  immune *screen* IS the signed `/immune/verdict` route (live 200). The `screen`
  tool maps to `/immune/verdict`. Disclosed in the adapter, never faked.
- **companion / llm** — expose no JSON `/v1/mcp/tools` catalog; tools are derived
  from the known live action routes (`/companion/{ask,act,recommend}`,
  `/llm/tiers`), each verified 200. Disclosed, not faked.
- **DSSE signer** — runs in honest `PLACEHOLDER` mode unless `HATUN_MCP_SIGNING_KEY`
  (PEM) is injected as a Space secret.
- **Sigstore Rekor** transparency-log inclusion remains a disclosed placeholder
  boundary (Doctrine v12 §2).

## Correction (this PR, 2026-06-16)

The three previously-codenamed backends (sentra/rosie/amaru) were **purged** — every
old route now returns 404. Hatun-MCP was repointed to the **live honest a11oy twins**
(immune / companion / llm on `a-11-oy.com`), each verified **200** before wiring. The
two codename tool names were renamed to honest names (`szl_immune_scan`,
`szl_companion_reason`) and the old names are no longer served. See `DEPRECATED.md`.

## What's Deprecated

- `szl_sentra_scan` → **`szl_immune_scan`** (old name not served; see DEPRECATED.md)
- `szl_rosie_reason` → **`szl_companion_reason`** (old name not served; see DEPRECATED.md)

---

*Co-Authored-By: Perplexity Computer Agent*
*Doctrine v11 — 749/14/163 — c7c0ba17*
