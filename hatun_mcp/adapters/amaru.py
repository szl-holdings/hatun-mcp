"""
hatun_mcp.adapters.amaru — Amaru cortex (memory + reasoner).

LIVE as of 2026-06-03: /api/amaru/v1/mcp/tools returns a JSON catalog of 4 tools
(ask, recall, semantic_search, cite). Uses the default fetch_catalog().

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

from .base import OrganAdapter


class AmaruAdapter(OrganAdapter):
    organ = "amaru"
    base_env = "SZL_AMARU_URL"
    base_default = "https://szlholdings-amaru.hf.space"
    catalog_route = "/api/amaru/v1/mcp/tools"

    def call_routes(self, tool: str) -> list[str]:
        return [
            "/api/amaru/v1/mcp/call",
            f"/api/amaru/v1/{tool}",
            "/v1/brain/jack",
            "/api/amaru/v1/rag",
        ]
