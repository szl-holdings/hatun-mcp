"""Adapter wiring tests with MOCKED organ endpoints (no real network).

Verifies:
  * a live JSON catalog (amaru/killinchu shape) parses into <organ>_<tool> names;
  * a string-name catalog (rosie shape) parses with defaulted schemas;
  * a paused organ (a11oy 503) yields reachable=False + zero tools (honest);
  * sentra derives tools from /gates (no /v1/mcp/tools JSON);
  * killinchu marks cue/halt_drone as 2-person;
  * register_organ_tools registers <organ>_<tool> for live organs and an honest
    <organ>_status tool for unreachable ones.

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
    AmaruAdapter, KillinchuAdapter, RosieAdapter, SentraAdapter, A11oyAdapter,
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


def test_amaru_live_catalog(monkeypatch):
    table = {"/api/amaru/v1/mcp/tools": (200, {"tools": [
        {"name": "ask", "description": "RAG", "inputSchema": {"type": "object"}},
        {"name": "recall"}, {"name": "semantic_search"}, {"name": "cite"},
    ]}, "application/json")}
    _patch(monkeypatch, table)
    cat = asyncio.run(AmaruAdapter().fetch_catalog())
    assert cat.reachable is True
    names = [t.mcp_name for t in cat.tools]
    assert names == ["amaru_ask", "amaru_recall", "amaru_semantic_search", "amaru_cite"]


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


def test_rosie_string_name_catalog(monkeypatch):
    table = {"/api/rosie/v1/mcp/tools": (200, {"count": 3, "tools":
             ["lambda_gate", "doctrine_gate", "memory_query"]}, "application/json")}
    _patch(monkeypatch, table)
    cat = asyncio.run(RosieAdapter().fetch_catalog())
    assert cat.reachable is True
    assert [t.mcp_name for t in cat.tools] == \
        ["rosie_lambda_gate", "rosie_doctrine_gate", "rosie_memory_query"]
    # governance-critical flags set for lambda_gate / doctrine_gate
    crit = {t.name for t in cat.tools if t.governance_critical}
    assert "lambda_gate" in crit and "doctrine_gate" in crit


def test_a11oy_paused_is_honest_zero_tools(monkeypatch):
    table = {"/api/a11oy/v1/mcp/tools":
             (503, "The space is paused, ask a maintainer to restart it", "text/plain")}
    _patch(monkeypatch, table)
    cat = asyncio.run(A11oyAdapter().fetch_catalog())
    assert cat.reachable is False
    assert cat.tools == []
    assert "503" in str(cat.http_status) or "paused" in cat.reason.lower()


def test_sentra_spa_shell_rejected_then_gates_used(monkeypatch):
    # sentra's fetch_catalog reads /gates (not /v1/mcp/tools). Provide gates JSON.
    table = {"/api/sentra/v1/gates": (200, {"gates": [
        {"gate_id": "gate-01"}, {"gate_id": "gate-02"}, {"gate_id": "gate-03"},
    ]}, "application/json")}
    _patch(monkeypatch, table)
    cat = asyncio.run(SentraAdapter().fetch_catalog())
    assert cat.reachable is True
    names = [t.mcp_name for t in cat.tools]
    assert "sentra_gate_gate_01" in names
    assert "sentra_inspect" in names and "sentra_verdict" in names
    assert "/gates" in cat.source_route


def test_base_rejects_spa_html(monkeypatch):
    # The default base parser must reject a 200 HTML SPA shell as non-JSON (honest).
    table = {"/api/amaru/v1/mcp/tools": (200, "<!DOCTYPE html><html></html>", "text/html")}
    _patch(monkeypatch, table)
    cat = asyncio.run(AmaruAdapter().fetch_catalog())
    assert cat.reachable is False
    assert "non-json" in cat.reason.lower() or "spa" in cat.reason.lower()


def test_register_organ_tools_live_and_status(monkeypatch):
    """register_organ_tools must add <organ>_<tool> for live organs and an honest
    <organ>_status tool for unreachable ones."""
    table = {
        "/api/amaru/v1/mcp/tools": (200, {"tools": [{"name": "ask"}]}, "application/json"),
        "/api/a11oy/v1/mcp/tools": (503, "paused", "text/plain"),
        "/api/killinchu/v1/mcp/tools": (200, {"tools": [{"name": "detect"}]}, "application/json"),
        "/api/rosie/v1/mcp/tools": (200, {"tools": ["lambda_gate"]}, "application/json"),
        "/api/sentra/v1/gates": (200, {"gates": [{"gate_id": "gate-01"}]}, "application/json"),
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

    assert "amaru_ask" in registered
    assert "killinchu_detect" in registered
    assert "rosie_lambda_gate" in registered
    assert "sentra_gate_gate_01" in registered
    # a11oy paused -> honest status tool, no a11oy_<gate> tools
    assert "a11oy_status" in registered
    assert not any(r.startswith("a11oy_gate") for r in registered)
    assert summary["a11oy"]["reachable"] is False
    assert summary["amaru"]["reachable"] is True
