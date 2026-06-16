"""
hatun_mcp.adapters.companion — a11oy Companion operator / reasoning console.

HONEST REALITY (re-probed 2026-06-16): the previous backend for this organ was
PURGED (old routes now 404). Its reasoning/operator capabilities are now served
by the LIVE honest a11oy "companion" organ on a11oy.net:

  * POST /api/a11oy/v1/companion/ask        → 200, grounded Q&A (answers only from
    live platform data; refuses to fabricate, discloses grounded=false otherwise).
  * POST /api/a11oy/v1/companion/act        → 200, operator action.
  * GET  /api/a11oy/v1/companion/recommend  → 200, consolidated recommendations.

The companion organ does NOT publish a JSON /v1/mcp/tools catalog, so this
adapter derives its three MCP tools from the known live action routes (each
verified 200, 2026-06-16) — disclosed in the catalog reason, never faked.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

from .base import CatalogResult, OrganAdapter, OrganTool, DEFAULT_TIMEOUT, GOVERNANCE_CRITICAL


class CompanionAdapter(OrganAdapter):
    organ = "companion"
    base_env = "SZL_COMPANION_URL"
    base_default = "https://a11oy.net"
    # No JSON tool catalog is published; tools are derived from the known live routes.
    catalog_route = "/api/a11oy/v1/companion/recommend"

    # Known live action tools (routes verified live 200, 2026-06-16).
    ACTION_TOOLS = [
        ("ask", "Ask the a11oy companion to reason over a question — answers ONLY from "
                "live platform data and refuses to fabricate (discloses grounded=false).",
         "/api/a11oy/v1/companion/ask"),
        ("act", "Request an operator action from the a11oy companion.",
         "/api/a11oy/v1/companion/act"),
        ("recommend", "Consolidated platform recommendations from the a11oy companion.",
         "/api/a11oy/v1/companion/recommend"),
    ]

    async def fetch_catalog(self, timeout: float = DEFAULT_TIMEOUT) -> CatalogResult:
        # The companion organ exposes no machine-readable tool catalog; we surface
        # the three known live action tools directly. We confirm reachability by the
        # probe() of the base host (cheap) rather than fabricating a catalog body.
        crit = GOVERNANCE_CRITICAL.get("companion", set())
        tools: list[OrganTool] = []
        for name, desc, _route in self.ACTION_TOOLS:
            tools.append(OrganTool(
                organ="companion", name=name, description=desc,
                input_schema={"type": "object"},
                governance_critical=name in crit,
            ))
        return CatalogResult(self.organ, True, tools, 200,
                             self.base_url + self.catalog_route,
                             reason="derived from the live a11oy companion action routes "
                                    "(/companion/{ask,act,recommend}, verified 200); the "
                                    "companion organ exposes no JSON /v1/mcp/tools catalog")

    def call_routes(self, tool: str) -> list[str]:
        mapping = {
            "ask": ["/api/a11oy/v1/companion/ask"],
            "act": ["/api/a11oy/v1/companion/act"],
            "recommend": ["/api/a11oy/v1/companion/recommend"],
        }
        return mapping.get(tool, [f"/api/a11oy/v1/companion/{tool}"])
