"""AXLE secondary-oracle bridge tests (hermetic: no network, no AXLE key).

Asserts the SZL tweaks over a plain AXLE mirror:
  * fail-closed ABSTAIN: no key configured => honest axle_not_configured,
    never a pass, with the full governed envelope + Khipu receipt;
  * fixed allowlist: unknown endpoints are declined before any network call;
  * secondary-oracle framing on every result (authorizing: false, local
    kernel stays primary);
  * key hygiene: the bearer key is never echoed into any response;
  * the runtime tool catalog stays in parity with the server card (38).

SPDX-License-Identifier: Apache-2.0
"""
import asyncio
import json
import os
import sys

import pytest

os.environ.setdefault("HATUN_MCP_DISABLE_DYNAMIC", "true")  # hermetic: no organ probing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hatun_mcp import axle as A  # noqa: E402
from hatun_mcp import server as S  # noqa: E402
from hatun_mcp.server_http import _server_card  # noqa: E402


def setup_module(_):
    S._set_test_context(client_id="szl_test_axle", scope="admin")


def _clear_axle_key(monkeypatch):
    monkeypatch.delenv("AXLE_API_KEY", raising=False)
    monkeypatch.delenv("HATUN_MCP_AXLE_API_KEY", raising=False)


AXLE_TOOL_NAMES = (
    "szl_axle_status", "szl_axle_environments", "szl_axle_verify_proof",
    "szl_axle_check", "szl_axle_disprove", "szl_axle_sorry2lemma",
    "szl_axle_extract_proof_states", "szl_axle_call",
)


def test_axle_endpoint_allowlist_is_the_full_16():
    assert A.AXLE_ENDPOINTS == frozenset({
        "verify_proof", "check", "extract_theorems", "extract_decls",
        "extract_proof_states", "rename", "theorem2lemma", "theorem2sorry",
        "merge", "simplify_theorems", "repair_proofs", "have2lemma",
        "have2sorry", "sorry2lemma", "disprove", "normalize",
    })


def test_axle_timeout_clamped_to_upstream_max():
    assert A._clamp_timeout(10_000) == A.AXLE_MAX_TIMEOUT_SECONDS
    assert A._clamp_timeout(0) == 1.0
    assert A._clamp_timeout("not-a-number") == A.AXLE_DEFAULT_TIMEOUT_SECONDS


def test_axle_not_configured_is_fail_closed_abstain(monkeypatch):
    _clear_axle_key(monkeypatch)
    result = asyncio.run(A.axle_run("verify_proof", {"content": "theorem main : True := rfl"}))
    assert result.ok is False
    assert result["error"] == "axle_not_configured"
    env = result["data"]
    assert env["oracle"] == "axle"
    assert env["authorizing"] is False
    assert env["local_kernel_primary"] is True
    assert env["estate_reading"] == "abstain"
    assert env["axle"] is None  # no fabricated verdict, ever


def test_axle_allowlist_rejects_before_network(monkeypatch):
    _clear_axle_key(monkeypatch)
    result = asyncio.run(A.axle_run("make_coffee", {}))
    assert result["error"] == "axle_endpoint_not_allowlisted"
    assert result["data"]["estate_reading"] == "abstain"


def test_axle_oversized_payload_rejected_before_network(monkeypatch):
    monkeypatch.setenv("AXLE_API_KEY", "test-key-bridge-not-a-secret")
    big = {"content": "x" * (A.AXLE_MAX_CONTENT_BYTES + 1)}
    result = asyncio.run(A.axle_run("check", big))
    assert result["error"] == "axle_payload_rejected"
    assert result["data"]["estate_reading"] == "abstain"


def test_axle_reading_classification():
    assert A._reading("verify_proof", {"okay": True}) == "corroborated"
    assert A._reading("verify_proof", {"okay": False}) == "not_corroborated"
    assert A._reading("check", {"okay": True, "failed_declarations": ["t1"]}) \
        == "not_corroborated"
    assert A._reading("verify_proof", {"okay": True, "user_error": "bad"}) \
        == "not_corroborated"
    assert A._reading("disprove", {"content": "..."}) == "reading_needs_caller_review"


def _assert_governed_abstain(out):
    assert out["status"] == "failure"
    assert out["khipu_receipt"]["chain_verified"] is True
    assert out["dsse"]["_mode"] in ("ECDSA-P256", "PLACEHOLDER")
    data = out["data"]
    assert data["oracle"] == "axle"
    assert data["role"] == "secondary_corroborating"
    assert data["authorizing"] is False
    assert data["local_kernel_primary"] is True
    assert data["estate_reading"] == "abstain"
    assert data["axle"] is None  # honest: no verdict without a verdict


def test_tool_status_abstains_without_key(monkeypatch):
    _clear_axle_key(monkeypatch)
    out = asyncio.run(_call_tool("szl_axle_status", {}))
    _assert_governed_abstain(out)
    assert out["data"]["axle_error"] == "axle_not_configured"


def test_tool_verify_proof_abstains_without_key(monkeypatch):
    _clear_axle_key(monkeypatch)
    out = asyncio.run(_call_tool("szl_axle_verify_proof", {
        "formal_statement": "def A : Nat\ntheorem main : A = 5 := sorry",
        "content": "def A : Nat := 5\ntheorem main : A = 5 := rfl",
        "environment": "lean-4.34.0",
    }))
    _assert_governed_abstain(out)


def test_tool_call_rejects_unknown_endpoint(monkeypatch):
    _clear_axle_key(monkeypatch)
    out = asyncio.run(_call_tool("szl_axle_call", {
        "endpoint": "resend_email", "payload": {},
    }))
    _assert_governed_abstain(out)
    assert out["data"]["axle_error"] == "axle_endpoint_not_allowlisted"


def test_tool_key_is_never_echoed(monkeypatch):
    _clear_axle_key(monkeypatch)
    monkeypatch.setenv("AXLE_API_KEY", "test-secret-bridge-never-echoed")
    # Unroutable test host: transport must fail CLOSED and stay sanitized.
    monkeypatch.setattr(A, "AXLE_BASE", "https://axle.invalid.test")
    out = asyncio.run(_call_tool("szl_axle_status", {}))
    blob = json.dumps(out)
    assert "test-secret-bridge-never-echoed" not in blob
    assert "Bearer" not in blob
    assert out["data"]["estate_reading"] == "abstain"


def test_tools_list_parity_with_server_card():
    async def _lists():
        tools = await S.mcp.list_tools()
        runtime = sorted(t.name for t in tools)
        card = sorted(t["name"] for t in _server_card()["tools"])
        return runtime, card
    runtime, card = asyncio.run(_lists())
    assert runtime == card, "runtime tools/list and the server card must match exactly"
    assert len(runtime) == 38
    for name in AXLE_TOOL_NAMES:
        assert name in runtime, f"missing {name}"


async def _call_tool(name: str, args: dict) -> dict:
    from mcp import Client as connect
    async with connect(S.mcp) as client:
        result = await client.call_tool(name, args)
        assert result.is_error is False, result.content
        return json.loads(result.content[0].text)
