"""hatun_mcp.tools — PURIQ governance gates promoted to first-class MCP tools.

Registers, against the shared FastMCP instance in hatun_mcp.server, five tools that
wrap the REAL governance primitives in hatun_mcp.governance:

  * yuyay_gate_check      — 13-axis Yuyay gate + Λ contribution + receipt
  * khipu_append_and_verify — append a Khipu link and recompute-verify the chain
  * dsse_sign             — real ECDSA P-256 DSSE envelope (UNSIGNED when no key)
  * mesh_quorum_status    — Byzantine n>=3f+1 quorum over organ ids
  * puriq_master          — THE named entrypoint: Yuyay-13 -> quorum -> Khipu -> DSSE

SPDX-License-Identifier: Apache-2.0
Author: Yachay (CTO authority) - Built by Perplexity Computer Agent - 2026-06-03
"""
from __future__ import annotations

__all__ = ["register_axle_bridge", "register_governance_tools"]


def register_governance_tools(mcp, khipu, signer, clients):
    """Register the five governance tools on the given FastMCP instance.

    Imported lazily by hatun_mcp.server after its singletons exist so we reuse the
    SAME live Khipu chain / signer / client registry (no parallel state).
    """
    from .governance_tools import _install
    _install(mcp, khipu, signer, clients)


def register_axle_bridge(mcp, khipu, signer, clients):
    """Register the eight AXLE secondary-oracle bridge tools (2026-11-15 instill:
    AxiomMath's AXLE MCP surface consolidated under SZL doctrine). Same lazy
    pattern: reuses the live chain / signer / client registry."""
    from .axle_bridge import _install as _axle_install
    _axle_install(mcp, khipu, signer, clients)
