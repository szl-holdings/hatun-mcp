"""
hatun_mcp.adapters — one adapter per SZL organ.

Each adapter pulls its organ's live MCP tool catalog from
`/api/<organ>/v1/mcp/tools` and re-exposes the tools through the Hatun-MCP
governed pipeline. Adapters are HONEST about reachability: an organ whose Space
is paused or whose catalog route is not JSON registers ZERO tools plus a single
`<organ>_status` introspection tool that reports exactly why — never fabricated
stubs.

SPDX-License-Identifier: Apache-2.0
Author: Yachay (CTO authority) · Built by Perplexity Computer Agent · 2026-06-03
"""
from __future__ import annotations

from .base import (
    CatalogResult,
    OrganAdapter,
    OrganTool,
    ProbeResult,
    register_organ_tools,
)
from .a11oy import A11oyAdapter
from .amaru import AmaruAdapter
from .sentra import SentraAdapter
from .killinchu import KillinchuAdapter
from .rosie import RosieAdapter

ALL_ADAPTERS = {
    "a11oy": A11oyAdapter,
    "amaru": AmaruAdapter,
    "sentra": SentraAdapter,
    "killinchu": KillinchuAdapter,
    "rosie": RosieAdapter,
}


def build_adapters() -> dict[str, OrganAdapter]:
    """Instantiate one adapter per organ (uses env-overridable base URLs)."""
    return {name: cls() for name, cls in ALL_ADAPTERS.items()}


__all__ = [
    "CatalogResult",
    "OrganAdapter",
    "OrganTool",
    "ProbeResult",
    "register_organ_tools",
    "A11oyAdapter",
    "AmaruAdapter",
    "SentraAdapter",
    "KillinchuAdapter",
    "RosieAdapter",
    "ALL_ADAPTERS",
    "build_adapters",
]
