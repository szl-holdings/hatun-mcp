# hatun-mcp domain leader study r1 (propose-only)

Date: 2026-11-22. Method: web-verified 2026 leaders. Documentation only: no code, CI, config, or existing-PR status changes. All absorb actions are FUTURE and non-authorizing; implementation and merges remain separately reviewed and gated by the signature wall.

## Domain: CPU-only deferred action + stale-file contract witness (MCP server)

## Leaders studied (web-verified 2026-11-22)

1. **Model Context Protocol specification**: explicit tool-call lifecycle incl. deferred semantics. [Normative spec](https://modelcontextprotocol.info/specification/2025-06-18/).
2. **FastMCP** implementation patterns over the spec. [Community pattern](https://gofastmcp.com/getting-started/welcome).

## Absorb actions (FUTURE PROPOSALS, non-authorizing)

1. (MCP spec) Deferred-action tool calls carry explicit staleness contracts: deferred action id, defer time, expiry, and stale-handling declared up-front.
2. (spec discipline) CPU-only execution mode is a declared tool capability; CPU-bound work never blocks the witness loop; stale-file contract witness re-verifies before reporting freshness.
Read-only alignment: open PR #207 (CPU-only deferred action and stale-file contract witness); no status claim.

## Sources (accessed 2026-11-22)

- MCP specification: https://modelcontextprotocol.info/specification/2025-06-18/ (normative spec)
- FastMCP docs: https://gofastmcp.com/getting-started/welcome (community pattern, not normative)

## Do not do

Do not merge, bypass the signature wall, or claim implementation beyond this card.
