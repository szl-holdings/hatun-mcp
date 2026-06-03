"""
hatun_mcp.adapters.sentra — Sentra policy immune system.

HONEST REALITY (probed 2026-06-03): sentra's root returns 200, but
/api/sentra/v1/mcp/tools and /v1/mcp/tools return the single-page-application
HTML shell, NOT a JSON tool catalog. So the default JSON fetch would (correctly)
report 'non-JSON SPA shell'. Sentra DOES, however, expose a real JSON gates
catalog at /api/sentra/v1/gates (8 gates: gate-01..gate-08) plus live action
routes (/api/sentra/v1/inspect, /v1/verdict). This adapter overrides
fetch_catalog() to derive MCP tools from the gates catalog + the known action
tools — disclosed in the catalog source_route, never faked.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import json

import httpx

from .base import CatalogResult, OrganAdapter, OrganTool, DEFAULT_TIMEOUT, GOVERNANCE_CRITICAL


class SentraAdapter(OrganAdapter):
    organ = "sentra"
    base_env = "SZL_SENTRA_URL"
    base_default = "https://szlholdings-sentra.hf.space"
    catalog_route = "/api/sentra/v1/gates"  # gates, not mcp/tools (SPA shell there)

    # Known live action tools (real routes verified in sentra openapi.json).
    ACTION_TOOLS = [
        ("inspect", "Inline immune screen of code / SBOM / image.", "/api/sentra/v1/inspect"),
        ("verdict", "Signed policy verdict for an action.", "/api/sentra/v1/verdict"),
        ("doctrine_guard", "Doctrine-guard check.", "/api/sentra/v1/doctrine-guard"),
    ]

    async def fetch_catalog(self, timeout: float = DEFAULT_TIMEOUT) -> CatalogResult:
        route = self.base_url + self.catalog_route
        crit = GOVERNANCE_CRITICAL.get("sentra", set())
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                r = await c.get(route)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            return CatalogResult(self.organ, False, [], f"transport_error:{type(e).__name__}",
                                 route, reason=f"sentra unreachable: {e}")
        if r.status_code != 200:
            return CatalogResult(self.organ, False, [], r.status_code, route,
                                 reason=f"/gates returned {r.status_code}")
        try:
            body = r.json()
        except (json.JSONDecodeError, ValueError):
            return CatalogResult(self.organ, False, [], r.status_code, route,
                                 reason="sentra /gates returned non-JSON")

        gates = body.get("gates", body) if isinstance(body, dict) else body
        tools: list[OrganTool] = []
        if isinstance(gates, list):
            for g in gates:
                gid = (g.get("gate_id") or g.get("id") or g.get("name")) if isinstance(g, dict) else g
                if not gid:
                    continue
                gid_norm = str(gid).replace("-", "_")
                tools.append(OrganTool(
                    organ="sentra", name=f"gate_{gid_norm}",
                    description=(g.get("description", f"Sentra policy gate {gid}")
                                 if isinstance(g, dict) else f"Sentra policy gate {gid}"),
                    input_schema={"type": "object",
                                  "properties": {"action": {"type": "object"},
                                                 "context": {"type": "object"}}},
                    governance_critical=True,  # gate verdicts are governance-critical
                ))
        # Known action tools.
        for name, desc, _route in self.ACTION_TOOLS:
            tools.append(OrganTool(
                organ="sentra", name=name, description=desc,
                input_schema={"type": "object"},
                governance_critical=name in crit,
            ))
        return CatalogResult(self.organ, True, tools, r.status_code, route,
                             reason="derived from /api/sentra/v1/gates + known action routes "
                                    "(sentra does not expose a JSON /v1/mcp/tools catalog)")

    def call_routes(self, tool: str) -> list[str]:
        if tool.startswith("gate_"):
            return ["/api/sentra/v1/verdict", "/v1/verdict",
                    "/api/sentra/v1/inspect"]
        mapping = {
            "inspect": ["/api/sentra/v1/inspect", "/v1/inspect"],
            "verdict": ["/api/sentra/v1/verdict", "/v1/verdict"],
            "doctrine_guard": ["/api/sentra/v1/doctrine-guard", "/doctrine-guard"],
        }
        return mapping.get(tool, [f"/api/sentra/v1/{tool}", f"/v1/{tool}"])
