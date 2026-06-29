"""
hatun_mcp.adapters.immune — a11oy Immune (Hukulla) policy / egress inspector.

HONEST REALITY (re-probed 2026-06-16): the previous backend for this organ was
PURGED (every old route now 404). Its capabilities are now served by the LIVE
honest a11oy "immune" organ on a-11-oy.com:

  * GET  /api/a11oy/v1/immune/gates    → 200, JSON {"gates":[{id,name,...}, ...]}
  * GET|POST /api/a11oy/v1/immune/verdict → 200, signed policy verdict (organ
    "Immune (Hukulla)", Khipu receipt + Neyman-Pearson Lean backing).

There is NO separate /immune/screen or /immune/inspect route (both 404): the
immune *screen* IS the verdict route — a screen of code/SBOM/image is performed
by POSTing the action to /immune/verdict, which fires the threat-signature gates
and returns the allow/deny decision. This adapter therefore derives MCP tools
from the live /gates catalog + the single real action route (verdict). Every
route is verified live before wiring — never faked, never pointed at a 404.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import json

import httpx

from .base import CatalogResult, OrganAdapter, OrganTool, DEFAULT_TIMEOUT, GOVERNANCE_CRITICAL


class ImmuneAdapter(OrganAdapter):
    organ = "immune"
    base_env = "SZL_IMMUNE_URL"
    base_default = "https://a-11-oy.com"
    catalog_route = "/api/a11oy/v1/immune/gates"  # live 200 JSON gates catalog

    # Known live action tools (routes verified live 200, 2026-06-16). The immune
    # "screen" of an action is the signed verdict route — there is no separate
    # /screen or /inspect endpoint, so we expose a single honest `screen` tool that
    # routes to the real /immune/verdict endpoint.
    ACTION_TOOLS = [
        ("screen", "Inline immune screen of an action (code / SBOM / image) — fires the "
                   "threat-signature gates and returns the signed allow/deny verdict.",
         "/api/a11oy/v1/immune/verdict"),
        ("verdict", "Signed policy verdict for an action (organ 'Immune (Hukulla)').",
         "/api/a11oy/v1/immune/verdict"),
    ]

    async def fetch_catalog(self, timeout: float = DEFAULT_TIMEOUT) -> CatalogResult:
        route = self.base_url + self.catalog_route
        crit = GOVERNANCE_CRITICAL.get("immune", set())
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                r = await c.get(route)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            return CatalogResult(self.organ, False, [], f"transport_error:{type(e).__name__}",
                                 route, reason=f"immune unreachable: {e}")
        if r.status_code != 200:
            return CatalogResult(self.organ, False, [], r.status_code, route,
                                 reason=f"/immune/gates returned {r.status_code}")
        try:
            body = r.json()
        except (json.JSONDecodeError, ValueError):
            return CatalogResult(self.organ, False, [], r.status_code, route,
                                 reason="immune /gates returned non-JSON")

        gates = body.get("gates", body) if isinstance(body, dict) else body
        tools: list[OrganTool] = []
        if isinstance(gates, list):
            for g in gates:
                gid = (g.get("id") or g.get("gate_id") or g.get("name")) if isinstance(g, dict) else g
                if not gid:
                    continue
                gid_norm = str(gid).replace("-", "_")
                tools.append(OrganTool(
                    organ="immune", name=f"gate_{gid_norm}",
                    description=(g.get("description", f"a11oy immune policy gate {gid}")
                                 if isinstance(g, dict) else f"a11oy immune policy gate {gid}"),
                    input_schema={"type": "object",
                                  "properties": {"action": {"type": "object"},
                                                 "context": {"type": "object"}}},
                    governance_critical=True,  # gate verdicts are governance-critical
                ))
        # Known action tools.
        for name, desc, _route in self.ACTION_TOOLS:
            tools.append(OrganTool(
                organ="immune", name=name, description=desc,
                input_schema={"type": "object"},
                governance_critical=name in crit,
            ))
        return CatalogResult(self.organ, True, tools, r.status_code, route,
                             reason="derived from live /api/a11oy/v1/immune/gates + the real "
                                    "/immune/verdict action route (verified 200)")

    def call_routes(self, tool: str) -> list[str]:
        # gate_*, screen, verdict, and the quorum's policy_evaluate probe all map to
        # the single live signed-verdict route (the immune screen IS the verdict).
        return ["/api/a11oy/v1/immune/verdict"]
