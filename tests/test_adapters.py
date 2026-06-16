"""Adapter wiring tests with MOCKED organ endpoints (no real network).

Verifies (post-2026-06-16 purge → honest-twin repoint):
  * llm adapter derives an `llm_tiers` tool;
  * companion adapter derives ask/act/recommend tools;
  * immune adapter derives tools from the live /immune/gates catalog + screen/verdict;
  * killinchu marks cue/halt_drone as 2-person;
  * register_organ_tools registers <organ>_<tool> for live organs and an honest
    <organ>_status tool for unreachable ones;
  * NO codename (sentra/rosie/amaru) tool name is ever registered.

SPDX-License-Identifier: Apache-2.0
"""
import asyncio
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hatun_mcp.adapters import (  # noqa: E402
    LlmAdapter, KillinchuAdapter, CompanionAdapter, ImmuneAdapter, A11oyAdapter,
)
from hatun_mcp.adapters.base import register_organ_tools  # noqa: E402


# ── A tiny mock transport: route URL -> (status, json_or_text, content_type) ────
class MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, table):
        self.table = table  # dict: path-substring -> (status, body, ctype)

    async def handle_async_request(self, request):
        url = str(request.url)
        for key, (status, body, ctype) in self.table.items():
            if key in url:
                content = body.encode() if isinstance(body, str) else json.dumps(body).encode()
                return httpx.Response(status, content=content,
                                      headers={"content-type": ctype})
        return httpx.Response(404, content=b'{"detail":"not found"}',
                              headers={"content-type": "application/json"})


def _patch(monkeypatch, table):
    mt = MockTransport(table)
    real_init = httpx.AsyncClient.__init__

    def init(self, *a, **kw):
        kw["transport"] = mt
        kw.pop("follow_redirects", None)
        real_init(self, *a, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", init)


def test_llm_tiers_catalog(monkeypatch):
    table = {"/api/a11oy/v1/llm/tiers": (200, {"count": 2, "tiers": [
        {"id": "claude_sonnet_4_6", "rank": 0}, {"id": "gpt_5_5", "rank": 4},
    ]}, "application/json")}
    _patch(monkeypatch, table)
    cat = asyncio.run(LlmAdapter().fetch_catalog())
    assert cat.reachable is True
    names = [t.mcp_name for t in cat.tools]
    assert names == ["llm_tiers"]


def test_killinchu_two_person_flag(monkeypatch):
    table = {"/api/killinchu/v1/mcp/tools": (200, {"tools": [
        {"name": "detect"}, {"name": "evaluate"},
        {"name": "cue", "requires_two_person": True},
        {"name": "halt_drone", "requires_two_person": True},
    ]}, "application/json")}
    _patch(monkeypatch, table)
    cat = asyncio.run(KillinchuAdapter().fetch_catalog())
    two = {t.name for t in cat.tools if t.requires_two_person}
    assert two == {"cue", "halt_drone"}


def test_companion_action_tools(monkeypatch):
    # The companion organ exposes no JSON catalog; the adapter surfaces the three
    # known live action tools directly.
    cat = asyncio.run(CompanionAdapter().fetch_catalog())
    assert cat.reachable is True
    names = [t.mcp_name for t in cat.tools]
    assert names == ["companion_ask", "companion_act", "companion_recommend"]
    assert "/companion/" in cat.reason


def test_immune_gates_and_actions(monkeypatch):
    # immune.fetch_catalog reads /immune/gates (live JSON) + screen/verdict actions.
    table = {"/api/a11oy/v1/immune/gates": (200, {"gates": [
        {"id": "gate-01"}, {"id": "gate-02"}, {"id": "gate-03"},
    ]}, "application/json")}
    _patch(monkeypatch, table)
    cat = asyncio.run(ImmuneAdapter().fetch_catalog())
    assert cat.reachable is True
    names = [t.mcp_name for t in cat.tools]
    assert "immune_gate_gate_01" in names
    assert "immune_screen" in names and "immune_verdict" in names
    assert "/immune/gates" in cat.source_route


def test_immune_screen_routes_to_verdict():
    # There is no /immune/screen route; the screen IS the verdict route.
    routes = ImmuneAdapter().call_routes("screen")
    assert routes == ["/api/a11oy/v1/immune/verdict"]


def test_a11oy_unreachable_is_honest_zero_tools(monkeypatch):
    table = {"/api/a11oy/v1/mcp/tools":
             (404, '{"detail":"not found"}', "application/json")}
    _patch(monkeypatch, table)
    cat = asyncio.run(A11oyAdapter().fetch_catalog())
    assert cat.reachable is False
    assert cat.tools == []


def test_register_organ_tools_live_and_status(monkeypatch):
    """register_organ_tools must add <organ>_<tool> for live organs and an honest
    <organ>_status tool for unreachable ones — with HONEST names only."""
    table = {
        "/api/a11oy/v1/llm/tiers": (200, {"tiers": [{"id": "t0", "rank": 0}]}, "application/json"),
        "/api/a11oy/v1/mcp/tools": (404, "not found", "application/json"),
        "/api/killinchu/v1/mcp/tools": (200, {"tools": [{"name": "detect"}]}, "application/json"),
        "/api/a11oy/v1/immune/gates": (200, {"gates": [{"id": "gate-01"}]}, "application/json"),
    }
    _patch(monkeypatch, table)

    registered = []

    class FakeMCP:
        def tool(self, name=None):
            def deco(fn):
                registered.append(name or fn.__name__)
                return fn
            return deco

    async def fake_governed(**kw):
        return {"tool": kw["tool"], "status": "success"}

    from hatun_mcp.adapters import build_adapters
    summary = register_organ_tools(FakeMCP(), build_adapters(), fake_governed)

    assert "llm_tiers" in registered
    assert "killinchu_detect" in registered
    assert "companion_ask" in registered
    assert "immune_gate_gate_01" in registered and "immune_screen" in registered
    # a11oy flagship catalog absent -> honest status tool, no a11oy_<gate> tools
    assert "a11oy_status" in registered
    assert summary["a11oy"]["reachable"] is False
    assert summary["llm"]["reachable"] is True
    # NO codename tool name is ever registered.
    assert not any(r.startswith(("sentra", "rosie", "amaru")) for r in registered)


def test_no_codename_tool_names(monkeypatch):
    """Across all adapters, no registered MCP tool name carries a codename."""
    table = {
        "/api/a11oy/v1/llm/tiers": (200, {"tiers": [{"id": "t0"}]}, "application/json"),
        "/api/a11oy/v1/mcp/tools": (404, "x", "application/json"),
        "/api/killinchu/v1/mcp/tools": (200, {"tools": [{"name": "detect"}]}, "application/json"),
        "/api/a11oy/v1/immune/gates": (200, {"gates": [{"id": "gate-01"}]}, "application/json"),
    }
    _patch(monkeypatch, table)

    registered = []

    class FakeMCP:
        def tool(self, name=None):
            def deco(fn):
                registered.append(name or fn.__name__)
                return fn
            return deco

    async def fake_governed(**kw):
        return {"tool": kw["tool"], "status": "success"}

    from hatun_mcp.adapters import build_adapters
    register_organ_tools(FakeMCP(), build_adapters(), fake_governed)
    for codename in ("sentra", "rosie", "amaru", "jarvis"):
        assert not any(codename in r for r in registered), \
            f"codename '{codename}' leaked into a tool name: {registered}"
