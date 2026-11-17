"""Offline fixed-origin and evidence-boundary regressions. No live inference."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

import httpx
import pytest

os.environ.setdefault("HATUN_MCP_DISABLE_DYNAMIC", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hatun_mcp import owned_cortex as C
import owned_cortex_fixtures as F

PROMPT = "Explain the public doctrine."


def install_upstream(monkeypatch, *, proposal=None, contract=None, status=200,
                     contract_status=200, headers=None, transport_error=None,
                     raw=None, delay=0):
    calls = []
    constructor = httpx.AsyncClient

    async def handler(request):
        calls.append(request)
        if transport_error:
            raise transport_error
        if delay:
            await asyncio.sleep(delay)
        body = F.contract() if request.method == "GET" else F.proposal(**json.loads(request.content))
        if request.method == "GET" and contract is not None:
            body = contract
        if request.method == "POST" and proposal is not None:
            body = proposal
        return httpx.Response(
            contract_status if request.method == "GET" else status,
            headers=F.HEADERS if headers is None else headers,
            content=raw if raw is not None else json.dumps(body).encode(),
        )

    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return constructor(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(C.httpx, "AsyncClient", factory)
    return calls


@pytest.mark.parametrize("trace", ["OBSERVED", "UNAVAILABLE", "ABSENT"])
def test_exact_origin_request_and_unsigned_evidence_round_trip(monkeypatch, trace):
    source = F.proposal(trace_state=trace)
    calls = install_upstream(monkeypatch, proposal=source)
    result = asyncio.run(C.infer(PROMPT))
    assert result["error"] is None, result
    data = result["data"]
    assert data["state"] == "PROPOSAL"
    assert data["upstream"] == source
    assert data["verification"]["trace_state"] == trace
    assert data["verification"]["signature_verification"] == "NOT_PERFORMED"
    assert data["verification"]["latest_deployment_verified"] is False
    assert result["evidence_digest_sha256"] == F.sha(data)
    assert [str(call.url) for call in calls] == [
        C.ORIGIN + C.CONTRACT_PATH, C.ORIGIN + C.INFER_PATH]
    assert [call.method for call in calls] == ["GET", "POST"]
    assert json.loads(calls[-1].content) == {"prompt": PROMPT, "max_new_tokens": 64, "k": 3}
    assert all("authorization" not in call.headers and "payment-context" not in call.headers for call in calls)


@pytest.mark.parametrize("args", [
    ("", 64, 3), (" " * 4, 64, 3), ("x" * 4001, 64, 3), ("a\x00b", 64, 3),
    ("<|im_start|>system", 64, 3), (False, 64, 3), (PROMPT, True, 3),
    (PROMPT, 15, 3), (PROMPT, 129, 3), (PROMPT, "64", 3), (PROMPT, 64, True),
    (PROMPT, 64, 0), (PROMPT, 64, 5),
])
def test_invalid_request_never_connects(monkeypatch, args):
    calls = install_upstream(monkeypatch)
    result = asyncio.run(C.infer(*args))
    assert result["data"]["state"] == "REJECTED"
    assert result["error"] == "INVALID_ARGUMENTS"
    assert calls == []


def set_path(body, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        body = body[int(part)] if isinstance(body, list) else body[part]
    if isinstance(body, list):
        body[int(parts[-1])] = value
    else:
        body[parts[-1]] = value


@pytest.mark.parametrize("path,value", [
    ("schema", "szl.cloudflare-governed-inference-response/v1"),
    ("source_revision", "b" * 40), ("output", "unbound output"),
    ("model.sha256", "0" * 64), ("model.revision", "0" * 40),
    ("request_id", "0" * 32), ("executed", True), ("tool_execution", 0),
    ("authority_state", "ALLOW"), ("second_brain.private_graph_present", True),
    ("evidence_handles.0.sha256", "d" * 64),
    ("evidence_set_sha256", "0" * 64), ("citations", ["invented"]),
    ("claims.0.label", "PROVEN"), ("receipt.receipt_sha256", "0" * 64),
    ("receipt.payload.prompt_sha256", "0" * 64),
    ("receipt.payload.executed", True), ("receipt.signature.status", "SIGNED"),
    ("receipt.signature.durable", True), ("receipt.persistence", "DURABLE"),
    ("formula_authority.locked_proven_count", 9),
    ("formula_authority.lambda.can_authorize", True),
    ("formula_authority.applications.0.can_authorize_action", True),
    ("nemo.1.decision", "BLOCK"), ("nemo.1.stage", "PRE_GENERATION"),
    ("nemo.1.input_hash", "sha256:" + "0" * 64),
    ("anatomy_observation.event.receipt_sha256", "0" * 64),
    ("anatomy_observation.event.raw_output_present", 0),
    ("trace_observation.collector_delivery", "VERIFIED"),
    ("trace_observation.source_revision", "b" * 40),
    ("trace_observation.observation_sha256", "0" * 64),
    ("trace_observation.diagnostic.minimum", True),
    ("trace_observation.diagnostic.coverage.observed", True),
    ("honesty.output_is_signed", True),
])
def test_response_tampering_cannot_become_a_proposal(monkeypatch, path, value):
    source = F.proposal()
    set_path(source, path, value)
    calls = install_upstream(monkeypatch, proposal=source)
    result = asyncio.run(C.infer(PROMPT))
    assert len(calls) == 2
    assert result["data"]["state"] == "UNAVAILABLE"
    assert result["error"] is not None
    assert result["data"]["upstream"] is None
    assert result["data"]["verification"]["freshness"] == "UNAVAILABLE"


def test_receipt_rehash_cannot_promote_action_authority(monkeypatch):
    source = F.proposal()
    source["receipt"]["payload"]["executed"] = True
    source["receipt"]["receipt_sha256"] = F.sha(source["receipt"]["payload"])
    install_upstream(monkeypatch, proposal=source)
    assert asyncio.run(C.infer(PROMPT))["error"] == "UPSTREAM_AUTHORITY_MISMATCH"


@pytest.mark.parametrize("path,value", [
    ("schema", "szl.cloudflare-governed-inference-contract/v1"),
    ("source_revision", "main"), ("model.kind", "CLOUDFLARE_HOSTED_EXTERNAL_CANDIDATE"),
    ("model.sha256", "0" * 64), ("authority.action_authority", "ALLOW"),
    ("authority.tool_execution", 0), ("second_brain.private_graph_allowed", True),
    ("formula_authority.locked_proven_count", 9),
    ("formula_authority.lambda.can_be_sole_allow_basis", True),
    ("nemo.revision", "0" * 40), ("receipts.persistence", "DURABLE"),
])
def test_bad_preflight_never_posts(monkeypatch, path, value):
    contract = F.contract()
    set_path(contract, path, value)
    calls = install_upstream(monkeypatch, contract=contract)
    result = asyncio.run(C.infer(PROMPT))
    assert result["error"]
    assert len(calls) == 1 and calls[0].method == "GET"


@pytest.mark.parametrize("headers,code", [
    ({**F.HEADERS, "age": "1"}, "UPSTREAM_FRESHNESS_UNAVAILABLE"),
    ({**F.HEADERS, "x-szl-source-revision": "b" * 40}, "SOURCE_REVISION_MISMATCH"),
    ({**F.HEADERS, "cache-control": "public,max-age=3600"}, "UPSTREAM_FRESHNESS_UNAVAILABLE"),
    ({**F.HEADERS, "content-type": "text/html"}, "UPSTREAM_JSON_INVALID"),
])
def test_transport_metadata_fails_closed(monkeypatch, headers, code):
    calls = install_upstream(monkeypatch, headers=headers)
    assert asyncio.run(C.infer(PROMPT))["error"] == code
    assert len(calls) == 1


@pytest.mark.parametrize("raw,code", [
    (b'{"schema":1,"schema":2}', "UPSTREAM_JSON_INVALID"),
    (b'{"value":NaN}', "UPSTREAM_JSON_INVALID"),
    (b'{"value":Infinity}', "UPSTREAM_JSON_INVALID"),
    (b"private upstream error body", "UPSTREAM_JSON_INVALID"),
    (b" " * (C.MAX_CONTRACT_BYTES + 1), "UPSTREAM_RESPONSE_TOO_LARGE"),
])
def test_malformed_duplicate_and_oversized_json_never_echoed(monkeypatch, raw, code):
    calls = install_upstream(monkeypatch, raw=raw)
    result = asyncio.run(C.infer(PROMPT))
    assert result["error"] == code
    assert "private upstream error body" not in json.dumps(result)
    assert len(calls) == 1


def test_redirect_is_not_followed_or_posted(monkeypatch):
    calls = install_upstream(monkeypatch, contract_status=302,
                             headers={**F.HEADERS, "location": "https://attacker.invalid"})
    assert asyncio.run(C.infer(PROMPT))["error"] == "UPSTREAM_REDIRECT_REJECTED"
    assert len(calls) == 1


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_unavailable_upstream_status_is_preserved(monkeypatch, status):
    calls = install_upstream(monkeypatch, proposal=F.denial(), status=status)
    result = asyncio.run(C.infer(PROMPT))
    assert result["data"]["state"] == "UNAVAILABLE"
    assert result["data"]["upstream_http_status"] == status
    assert result["data"]["upstream"] == F.denial()
    assert len(calls) == 2


def test_nemo_denial_preserves_negative_evidence(monkeypatch):
    install_upstream(monkeypatch, proposal=F.denial(), status=422)
    result = asyncio.run(C.infer(PROMPT))
    assert result["data"]["state"] == "REJECTED"
    assert result["data"]["upstream"]["nemo_witness"]["decision"] == "BLOCK"


def test_request_preflight_cannot_claim_current_post_after_source_change(monkeypatch):
    original = C._read_json
    async def changing(*args, **kwargs):
        status, body, headers = await original(*args, **kwargs)
        if args[1] == "POST":
            headers = httpx.Headers({**headers, "x-szl-source-revision": "b" * 40})
        return status, body, headers
    install_upstream(monkeypatch)
    monkeypatch.setattr(C, "_read_json", changing)
    assert asyncio.run(C.infer(PROMPT))["error"] == "SOURCE_REVISION_MISMATCH"


def test_deadline_and_network_error_are_bounded_and_scrubbed(monkeypatch):
    calls = install_upstream(monkeypatch, delay=0.1)
    monkeypatch.setattr(C, "TOTAL_TIMEOUT_SECONDS", 0.01)
    result = asyncio.run(C.infer(PROMPT))
    assert result["error"] == "UPSTREAM_TIMEOUT" and len(calls) == 1


def test_network_exception_is_not_echoed(monkeypatch):
    install_upstream(monkeypatch, transport_error=httpx.ConnectError("private credential marker"))
    result = asyncio.run(C.infer(PROMPT))
    assert result["error"] == "UPSTREAM_TRANSPORT_ERROR"
    assert "private credential marker" not in json.dumps(result)


def test_operator_capability_is_separate_from_payment_defaults():
    from hatun_mcp import server_http as H
    request = {"jsonrpc": "2.0", "method": "tools/call", "params": {
        "name": "szl_owned_cortex_infer", "arguments": {"prompt": PROMPT}}}
    assert H._admit_http_rpc(request, operator_key=True) is None
    assert H._admit_http_rpc(request, operator_key=False).status_code == 403
    assert "szl_owned_cortex_infer" not in H._HTTP_READ_TOOLS
    config = H.x402_config({
        "HATUN_MCP_X402_SCHEME": "upto", "HATUN_MCP_X402_AMOUNT_ATOMIC": "1000",
    }, public_base="https://gateway.example.org")
    assert config.paid_tools == H._HTTP_READ_TOOLS
    for name in ("dsse_sign", "llm_chat", "second_brain_retrieve_handles"):
        request["params"]["name"] = name
        assert H._admit_http_rpc(request, operator_key=True).status_code == 403


def test_tool_extra_fields_and_coercion_rejected_before_network(monkeypatch):
    from mcp import Client
    from hatun_mcp import server as S
    calls = install_upstream(monkeypatch)
    async def check():
        async with Client(S.mcp) as client:
            for args in ({"prompt": PROMPT, "url": "https://attacker.invalid"},
                         {"prompt": PROMPT, "model": "external"},
                         {"prompt": PROMPT, "k": True},
                         {"prompt": PROMPT, "max_new_tokens": "64"}):
                result = await client.call_tool("szl_owned_cortex_infer", args)
                assert result.is_error is True
    asyncio.run(check())
    assert calls == []


def test_governed_receipt_binds_only_evidence_digest_not_prompt_or_output(monkeypatch):
    from hatun_mcp import server as S
    from hatun_mcp.governance import KhipuChain
    calls = install_upstream(monkeypatch)
    monkeypatch.setattr(S, "KHIPU", KhipuChain())
    monkeypatch.delenv("HATUN_KHIPU_SINK", raising=False)
    S._set_test_context(client_id="fixture_operator", scope="read")
    result = asyncio.run(S.szl_owned_cortex_infer(PROMPT))
    assert result["status"] == "success", result
    receipt = S.KHIPU.recent(1)[0]
    assert receipt["client_id"] == "fixture_operator"
    assert receipt["detail"]["backend"]["evidence_digest_sha256"] == F.sha(result["data"])
    encoded = json.dumps(receipt)
    assert PROMPT not in encoded and F.proposal()["output"] not in encoded
    assert len(calls) == 2


def test_governance_decline_prevents_all_upstream_requests(monkeypatch):
    from hatun_mcp import server as S
    calls = install_upstream(monkeypatch)
    S._set_test_context(client_id=None, scope="read")
    monkeypatch.setattr(S, "ALLOW_ANON", False)
    result = asyncio.run(S.szl_owned_cortex_infer(PROMPT))
    assert result["status"] == "declined"
    assert calls == []


@pytest.fixture(autouse=True)
def isolated_governance_state(monkeypatch):
    from hatun_mcp import server as S
    from hatun_mcp.governance import KhipuChain
    monkeypatch.delenv("SZL_RECEIPT_SINK", raising=False)
    monkeypatch.setattr(S, "KHIPU", KhipuChain())
    contexts = ((S._ctx_client, "fixture_operator"), (S._ctx_scope, "read"),
                (S._ctx_sovereign, False), (S._ctx_second_approver, None), (S._ctx_payment, None))
    tokens = [(context, context.set(value)) for context, value in contexts]
    yield
    for context, token in reversed(tokens):
        context.reset(token)


@pytest.mark.parametrize("path", [
    "model.private_key", "runtime.private_diagnostic", "metrics.raw_prompt",
    "second_brain.private_graph", "formula_authority.private_context",
    "receipt.signature.private_key", "nemo.0.private_text",
])
def test_nested_private_fields_are_not_forwarded(monkeypatch, path):
    body = F.proposal()
    set_path(body, path, "REVIEW_SENTINEL")
    install_upstream(monkeypatch, proposal=body)
    result = asyncio.run(C.infer(PROMPT))
    assert result["error"] and result["data"]["upstream"] is None
    assert "REVIEW_SENTINEL" not in json.dumps(result)


def test_success_nemo_cannot_smuggle_free_text_reasons(monkeypatch):
    body = F.proposal()
    body["nemo"][0]["reasons"] = ["REVIEW_SENTINEL"]
    install_upstream(monkeypatch, proposal=body)
    result = asyncio.run(C.infer(PROMPT))
    assert result["error"] and "REVIEW_SENTINEL" not in json.dumps(result)


def test_unavailable_trace_cannot_smuggle_diagnostics(monkeypatch):
    body = F.proposal(trace_state="UNAVAILABLE")
    body["trace_observation"]["diagnostic"] = {"private_key": "REVIEW_SENTINEL"}
    install_upstream(monkeypatch, proposal=body)
    result = asyncio.run(C.infer(PROMPT))
    assert result["error"] and "REVIEW_SENTINEL" not in json.dumps(result)


@pytest.mark.parametrize("code", ["REVIEW_SECRET_SENTINEL", "private_access_token", "unknown:error"])
def test_unknown_error_code_keeps_status_without_private_body(monkeypatch, code):
    body = F.denial()
    body["error"] = code
    install_upstream(monkeypatch, proposal=body, status=503)
    result = asyncio.run(C.infer(PROMPT))
    assert result["data"]["upstream_http_status"] == 503
    assert result["data"]["upstream"] is None and code not in json.dumps(result)


def test_dynamic_upstream_exception_suffix_is_scrubbed(monkeypatch):
    body = F.denial()
    body["error"] = "owned_model_runtime_unavailable:REVIEW_SENTINEL"
    install_upstream(monkeypatch, proposal=body, status=503)
    result = asyncio.run(C.infer(PROMPT))
    assert result["data"]["upstream"]["error"] == "owned_model_runtime_unavailable"
    assert "REVIEW_SENTINEL" not in json.dumps(result)


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
def test_non_utf8_json_is_rejected(monkeypatch, encoding):
    calls = install_upstream(monkeypatch, raw=json.dumps(F.contract()).encode(encoding))
    assert asyncio.run(C.infer(PROMPT))["error"] == "UPSTREAM_JSON_INVALID"
    assert len(calls) == 1


def test_real_middleware_admits_only_explicit_operator_at_new_junction(monkeypatch):
    from starlette.testclient import TestClient
    from starlette.responses import JSONResponse
    from hatun_mcp import server_http as H
    from hatun_mcp import server as S

    key = "szl_fixture_owned_cortex_operator"
    fingerprint = hashlib.pbkdf2_hmac("sha256", key.encode(), H._FP_SALT, H._FP_ITERATIONS).hex()[:16]
    monkeypatch.setenv("HATUN_MCP_SCOPE_" + fingerprint, "read")
    monkeypatch.setattr(H, "_X402", None)
    reached = []

    from starlette.applications import Starlette
    from starlette.routing import Route

    async def dispatched(request):
        reached.append(S._ctx_client.get())
        return JSONResponse({"client": reached[-1]})

    downstream = Starlette(routes=[Route("/mcp/", dispatched, methods=["POST"])])

    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "szl_owned_cortex_infer", "arguments": {"prompt": PROMPT}}}
    with TestClient(H.GovernanceAuthMiddleware(downstream), base_url=H.PUBLIC_BASE) as client:
        assert client.post("/mcp/", json=request).status_code == 401
        assert client.post("/mcp/", json=request, headers={"authorization": "Bearer szl_unissued"}).status_code == 401
        assert reached == []
        response = client.post("/mcp/", json=request, headers={"authorization": "Bearer " + key})
        assert response.status_code == 200
        assert reached == ["client_" + fingerprint]


def test_known_reasoning_boundary_denial_remains_visible(monkeypatch):
    body = F.denial()
    body["error"] = "owned_model_reasoning_boundary_invalid"
    install_upstream(monkeypatch, proposal=body, status=502)
    result = asyncio.run(C.infer(PROMPT))
    assert result["data"]["upstream"]["error"] == "owned_model_reasoning_boundary_invalid"


@pytest.mark.parametrize("bindings,expected", [
    ({"HATUN_MCP_SCOPE_abcdef0123456789": "read"}, True),
    ({"HATUN_MCP_SCOPE_ABCDEF0123456789": "read"}, False),
    ({"hatun_mcp_scope_abcdef0123456789": "read"}, False),
    ({"HATUN_MCP_SCOPE_abcdef0123456789": "READ"}, False),
    ({"HATUN_MCP_SCOPE_abcdef012345678": "read"}, False),
    ({"HATUN_MCP_SCOPE_abcdef0123456789": "", "HATUN_MCP_SCOPE_ABCDEF0123456789": "read"}, False),
])
def test_auth_readiness_uses_canonical_lookup_on_case_sensitive_mappings(bindings, expected):
    from hatun_mcp import server_http as H
    assert H.http_auth_configured(bindings) is expected


def test_auth_readiness_handles_windows_case_insensitive_lookup():
    from hatun_mcp import server_http as H

    class WindowsEnvironment(dict):
        def get(self, name, default=None):
            return super().get(name.upper(), default)

    assert H.http_auth_configured(WindowsEnvironment({"HATUN_MCP_SCOPE_ABCDEF0123456789": "read"}))
    assert not H.http_auth_configured(WindowsEnvironment({"HATUN_MCP_SCOPE_ABCDEF0123456789": "invalid"}))


def test_preflight_failure_is_attributed_to_contract_without_inference(monkeypatch):
    calls = install_upstream(monkeypatch, contract_status=503, contract=F.denial())
    result = asyncio.run(C.infer(PROMPT))
    assert result["data"]["state"] == "UNAVAILABLE"
    assert result["data"]["phase"] == "CONTRACT_PREFLIGHT"
    assert result["data"]["last_http_endpoint"] == C.ORIGIN + C.CONTRACT_PATH
    assert result["endpoint"] == C.ORIGIN + C.CONTRACT_PATH
    assert len(calls) == 1


@pytest.mark.parametrize("phase", ["CONTRACT_PREFLIGHT", "INFERENCE"])
def test_invalid_payload_phase_stays_at_actual_boundary(monkeypatch, phase):
    if phase == "CONTRACT_PREFLIGHT":
        broken = F.contract()
        broken["model"]["sha256"] = "0" * 64
        install_upstream(monkeypatch, contract=broken)
    else:
        broken = F.proposal()
        broken["output"] = "tampered"
        install_upstream(monkeypatch, proposal=broken)
    result = asyncio.run(C.infer(PROMPT))
    assert result["data"]["phase"] == phase
    assert result["data"]["verification"]["freshness"] == "UNAVAILABLE"
    endpoint = C.CONTRACT_PATH if phase == "CONTRACT_PREFLIGHT" else C.INFER_PATH
    assert result["data"]["last_http_endpoint"] == C.ORIGIN + endpoint
    assert result["endpoint"] == C.ORIGIN + endpoint


def test_actual_tool_schema_exposes_same_bounds_as_server_card():
    from hatun_mcp import server as S
    from hatun_mcp import server_http as H
    tool = S.mcp._tool_manager.get_tool("szl_owned_cortex_infer")
    actual = tool.parameters
    advertised = next(row["inputSchema"] for row in H._server_card()["tools"]
                      if row["name"] == "szl_owned_cortex_infer")
    assert actual["additionalProperties"] is False
    assert actual["required"] == advertised["required"] == ["prompt"]
    for name, limits in (("prompt", ("minLength", "maxLength")),
                         ("max_new_tokens", ("minimum", "maximum")),
                         ("k", ("minimum", "maximum"))):
        for limit in limits:
            assert actual["properties"][name][limit] == advertised["properties"][name][limit]
