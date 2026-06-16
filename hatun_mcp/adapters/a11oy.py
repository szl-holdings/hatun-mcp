"""
hatun_mcp.adapters.a11oy — A11oy policy + receipt substrate.

LIVE as of 2026-06-16 on https://a11oy.net. The a11oy platform now serves the
immune / companion / llm organs directly (the purged sentra/rosie/amaru backends).
The default fetch_catalog() reads /api/a11oy/v1/mcp/tools when present; if that
catalog route is not exposed it registers zero a11oy-flagship tools + one honest
a11oy_status tool (the immune/companion/llm organs surface their own tools). Each
a11oy policy gate is governance-critical and routed through the Byzantine quorum —
never fabricated stubs.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

from .base import OrganAdapter, GOVERNANCE_CRITICAL

# A gate-shaped tool is treated as governance-critical regardless of name.
GOVERNANCE_CRITICAL["a11oy"] |= {"router", "route"}


class A11oyAdapter(OrganAdapter):
    organ = "a11oy"
    base_env = "SZL_A11OY_URL"
    base_default = "https://a11oy.net"
    catalog_route = "/api/a11oy/v1/mcp/tools"

    def _parse_catalog_json(self, body, route, status):
        # Mark every a11oy tool governance-critical (gates + router), then defer to base.
        res = super()._parse_catalog_json(body, route, status)
        for t in res.tools:
            t.governance_critical = True
            if t.name.lower().startswith("gate") or "gate" in (t.description or "").lower():
                t.gate_required = True
        return res

    def call_routes(self, tool: str) -> list[str]:
        if tool.startswith("gate") or tool == "policy_evaluate":
            return ["/api/a11oy/v1/policy/evaluate", "/v1/policy/evaluate"]
        if tool in ("router", "route", "code_chat"):
            return ["/v1/router", "/api/a11oy/v1/llm/route"]
        return ["/api/a11oy/v1/mcp/call", f"/api/a11oy/v1/{tool}", f"/v1/{tool}"]
