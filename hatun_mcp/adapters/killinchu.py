"""
hatun_mcp.adapters.killinchu — Killinchu counter-UAS rule engine.

LIVE as of 2026-06-03: /api/killinchu/v1/mcp/tools returns a JSON catalog of 4
tools (detect, evaluate, cue, halt_drone). `cue` and `halt_drone` advertise
requires_two_person=true, so the base adapter routes them through the 2-person
Yuyay gate automatically.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

from .base import OrganAdapter


class KillinchuAdapter(OrganAdapter):
    organ = "killinchu"
    base_env = "SZL_KILLINCHU_URL"
    base_default = "https://szlholdings-killinchu.hf.space"
    catalog_route = "/api/killinchu/v1/mcp/tools"

    def call_routes(self, tool: str) -> list[str]:
        # Map known killinchu tools onto their documented action routes first.
        known = {
            "detect": ["/counter-uas/identify", "/v1/iff"],
            "evaluate": ["/api/killinchu/v1/evaluate", "/v1/evaluate"],
            "cue": ["/v1/cue", "/cue"],
            "halt_drone": ["/v1/halt", "/api/killinchu/v1/halt"],
        }
        routes = known.get(tool, [])
        routes += [
            "/api/killinchu/v1/mcp/call",
            f"/api/killinchu/v1/{tool}",
            f"/v1/{tool}",
        ]
        return routes
