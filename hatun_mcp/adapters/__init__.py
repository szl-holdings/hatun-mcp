"""
hatun_mcp.adapters — one adapter per SZL organ.

Each adapter pulls its organ's live capability catalog from the a11oy platform
and re-exposes the tools through the Hatun-MCP governed pipeline. Adapters are
HONEST about reachability: an organ whose route is not live registers ZERO tools
plus a single `<organ>_status` introspection tool that reports exactly why —
never fabricated stubs.

The three previously-codenamed organ backends were PURGED and are now served by
the live honest a11oy organs (immune / companion / llm), so the adapters are
named for those honest organ roles. See DEPRECATED.md for the old→new mapping.

SPDX-License-Identifier: Apache-2.0
Author: Yachay (CTO authority) · Built by Perplexity Computer Agent
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
from .llm import LlmAdapter
from .immune import ImmuneAdapter
from .killinchu import KillinchuAdapter
from .companion import CompanionAdapter

ALL_ADAPTERS = {
    "a11oy": A11oyAdapter,
    "llm": LlmAdapter,
    "immune": ImmuneAdapter,
    "killinchu": KillinchuAdapter,
    "companion": CompanionAdapter,
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
    "LlmAdapter",
    "ImmuneAdapter",
    "KillinchuAdapter",
    "CompanionAdapter",
    "ALL_ADAPTERS",
    "build_adapters",
]
