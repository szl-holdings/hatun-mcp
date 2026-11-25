# hatun-mcp — Domain Leader Study Card r1 (propose-only)

OUROBOROS pass 1 of 10 - 2026-11-25 - CTO web lane. Propose-only: never merge without owner GO.

## Domain leaders
- The Model Context Protocol specification (Anthropic; modelcontextprotocol.info specification; claude.com/docs/connectors/building/mcp): open standard for connecting AI assistants to tools and data sources.
- Anthropic reference server implementations + registry practice: canonical tool-schema, resource-URI and lifecycle patterns.

## Moat to absorb
- Spec-version pinned conformance receipts per tool (spec drift becomes an auditable diff, never silently absorbed).
- Standard MCP tool metadata shape carrying SZL-specific side-effect class, receipt type, fail-closed behavior (externally built clients stay correct without knowing estate doctrine).
- Loopback conformance harness (szl-hatun-conformance) wired as CI on every protocol-relevant change.

## Recommended upgrades (owner-gated)
1. README protocol-lineage section: spec URL chain + version pin table (spec version vs server version).
2. Per-tool frontmatter: side_effect_class, receipt_type, fail-closed behavior.
3. CI gate: MCP spec snapshot pin so spec releases surface as a visible diff.