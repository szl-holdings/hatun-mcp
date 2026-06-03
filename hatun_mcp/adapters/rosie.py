"""
hatun_mcp.adapters.rosie — Rosie operator console / reasoning mesh.

LIVE as of 2026-06-03: /api/rosie/v1/mcp/tools returns a JSON catalog of 12 tool
NAMES (string list, no per-tool schemas): lambda_gate, doctrine_gate, doi_bind,
bekenstein_bound, policy_evaluate, receipt_verify, ledger_append, cite_theorem,
mesh_inspect, memory_write, memory_query, workflow_start.

The base parser handles the string-name form and defaults each tool's input
schema to {"type": "object"} (disclosed: schemas not advertised by rosie). The
governance-critical names (lambda_gate, doctrine_gate, policy_evaluate) are
flagged for the Byzantine quorum path.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

from .base import OrganAdapter


class RosieAdapter(OrganAdapter):
    organ = "rosie"
    base_env = "SZL_ROSIE_URL"
    base_default = "https://szlholdings-rosie.hf.space"
    catalog_route = "/api/rosie/v1/mcp/tools"

    def call_routes(self, tool: str) -> list[str]:
        return [
            "/api/rosie/v1/mcp/call",
            f"/api/rosie/v1/{tool}",
            "/v1/brain/jack",
            "/api/rosie/v1/rag",
        ]
