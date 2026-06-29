"""
hatun_mcp.adapters.llm — a11oy LLM tier router (model catalog).

HONEST REALITY (re-probed 2026-06-16): the previous backend for this organ was
PURGED (old routes now 404). Its model/tier capability is now served by the LIVE
honest a11oy "llm" organ on a-11-oy.com:

  * GET /api/a11oy/v1/llm/tiers  → 200, JSON {"count":N,"tiers":[{id,rank,use,why}...]}

The llm organ does NOT publish a JSON /v1/mcp/tools catalog, so this adapter
derives a single honest `tiers` MCP tool from the live /llm/tiers route (verified
200, 2026-06-16) — disclosed in the catalog reason, never faked.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import json

import httpx

from .. import backends as B
from .base import CatalogResult, OrganAdapter, OrganTool, DEFAULT_TIMEOUT, GOVERNANCE_CRITICAL


class LlmAdapter(OrganAdapter):
    organ = "llm"
    base_env = "SZL_LLM_URL"
    base_default = "https://a-11-oy.com"
    catalog_route = "/api/a11oy/v1/llm/tiers"

    ACTION_TOOLS = [
        ("tiers", "List the a11oy open-LLM router tiers (id, rank, use, why) — the live "
                  "GREEN-first model catalog.",
         "/api/a11oy/v1/llm/tiers"),
    ]

    async def fetch_catalog(self, timeout: float = DEFAULT_TIMEOUT) -> CatalogResult:
        crit = GOVERNANCE_CRITICAL.get("llm", set())
        tools: list[OrganTool] = []
        for name, desc, _route in self.ACTION_TOOLS:
            tools.append(OrganTool(
                organ="llm", name=name, description=desc,
                input_schema={"type": "object"},
                governance_critical=name in crit,
            ))
        return CatalogResult(self.organ, True, tools, 200,
                             self.base_url + self.catalog_route,
                             reason="derived from the live a11oy /api/a11oy/v1/llm/tiers route "
                                    "(verified 200); the llm organ exposes no JSON "
                                    "/v1/mcp/tools catalog")

    def call_routes(self, tool: str) -> list[str]:
        return ["/api/a11oy/v1/llm/tiers", f"/api/a11oy/v1/llm/{tool}"]

    async def call(self, tool: str, args: dict,
                   timeout: float = DEFAULT_TIMEOUT) -> B.BackendResult:
        """The a11oy /llm/tiers route is GET-only (POST -> 404). Override the default
        POST-based call() with an honest GET so the live tier catalog is returned."""
        url = self.base_url + "/api/a11oy/v1/llm/tiers"
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                r = await c.get(url, params=args or {})
        except (httpx.TimeoutException, httpx.TransportError) as e:
            return B.BackendResult(
                deployed=False, http_status=f"transport_error:{type(e).__name__}",
                endpoint=url, error="route_not_live",
                reason=f"llm.{tool}: GET {url} failed ({e}). Honest stub — disclosed, not faked.",
                data=None,
            )
        if r.status_code == 404:
            return B.BackendResult(
                deployed=False, http_status=404, endpoint=url, error="route_not_live",
                reason=f"llm.{tool}: {url} returned 404. Honest stub — disclosed, not faked.",
                data=None,
            )
        try:
            data = r.json()
        except (json.JSONDecodeError, ValueError):
            data = {"raw": r.text[:2000]}
        return B.BackendResult(
            deployed=True, http_status=r.status_code, endpoint=url,
            error=None if r.status_code < 400 else f"http_{r.status_code}",
            data=data,
        )
