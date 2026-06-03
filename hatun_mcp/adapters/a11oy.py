"""
hatun_mcp.adapters.a11oy — A11oy policy + receipt substrate.

HONEST REALITY (probed 2026-06-03): the a11oy HF Space is PAUSED — every route
returns HTTP 503 with the body "The space is paused, ask a maintainer to restart
it". Therefore a11oy's catalog is UNREACHABLE and this adapter registers ZERO MCP
tools today. a11oy advertises (in its repo) 46 policy-gate modules + 11 MCP tools;
the mission's headline "49 a11oy gates -> 49 MCP tools" is BLOCKED on a FOUNDER
restart of the Space.

SELF-HEALING: the default fetch_catalog() already does the right thing — when
a11oy returns 200 with a JSON catalog at /api/a11oy/v1/mcp/tools, every advertised
gate is surfaced automatically (named a11oy_<tool> / a11oy_gate_<id>) on the next
server restart, with NO code change and NO fabricated stubs. Each a11oy policy
gate is governance-critical and is routed through the Byzantine quorum.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

from .base import OrganAdapter, GOVERNANCE_CRITICAL

# A gate-shaped tool is treated as governance-critical regardless of name.
GOVERNANCE_CRITICAL["a11oy"] |= {"router", "route"}


class A11oyAdapter(OrganAdapter):
    organ = "a11oy"
    base_env = "SZL_A11OY_URL"
    base_default = "https://szlholdings-a11oy.hf.space"
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
