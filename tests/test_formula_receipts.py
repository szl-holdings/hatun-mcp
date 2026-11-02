"""Offline formula bindings: real ephemeral signatures, no network/provider calls."""
import asyncio
import base64
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

os.environ.setdefault("HATUN_MCP_DISABLE_DYNAMIC", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hatun_mcp import server as S
from hatun_mcp.formula_receipts import (canonical_bytes, formula_request,
                                       verify_formula_response)
from hatun_mcp.governance import ClientRegistry, DsseSigner, KhipuChain

CHALLENGE = "caller_saved_challenge_001"
CLIENT = "fixture_operator"


class TestFormulaReceipts:
    @pytest.fixture(autouse=True)
    def isolate(self, monkeypatch):
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
        monkeypatch.setenv("HATUN_MCP_SIGNING_KEY", pem)
        monkeypatch.delenv("HATUN_MCP_SIGNING_KEY_PATH", raising=False)
        monkeypatch.delenv("SZL_RECEIPT_SINK", raising=False)
        monkeypatch.setattr(S, "SIGNER", DsseSigner())
        monkeypatch.setattr(S, "KHIPU", KhipuChain())
        monkeypatch.setattr(S, "CLIENTS", ClientRegistry())
        monkeypatch.setattr(S, "ALLOW_ANON", False)
        token = S._ctx_client.set(CLIENT)
        scope = S._ctx_scope.set("read")
        self.public = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        yield
        S._ctx_client.reset(token)
        S._ctx_scope.reset(scope)

    def invoke(self, **kwargs):
        return asyncio.run(S.szl_formula_evaluate(name="sigmoid", args={"x": 0}, **kwargs))

    def verify(self, out, **kwargs):
        expected = dict(trusted_public_key_pem=self.public, expected_client_id=CLIENT,
                        name="sigmoid", args={"x": 0})
        expected.update(kwargs)
        return verify_formula_response(out, **expected)

    def test_existing_call_gains_verifiable_binding_without_changing_result(self):
        out = self.invoke()
        assert out["data"]["value"] == 0.5
        assert self.verify(out)["status"] == "success"
        assert S.KHIPU.verify()

    def test_optional_caller_challenge_is_bound(self):
        out = self.invoke(receipt_challenge=CHALLENGE)
        self.verify(out, receipt_challenge=CHALLENGE)
        for nonce in (None, CHALLENGE + "different"):
            with pytest.raises(ValueError):
                self.verify(out, receipt_challenge=nonce)

    @pytest.mark.parametrize("field,changed", [
        ("data", {"name": "sigmoid", "value": 0.99}),
        ("backend", {"deployed": True, "endpoint": "altered"}),
        ("status", "failure"), ("tool", "other_tool")])
    def test_mutated_response_is_rejected(self, field, changed):
        out = self.invoke()
        self.verify(out)
        out[field] = changed
        with pytest.raises(ValueError):
            self.verify(out)

    @pytest.mark.parametrize("expected", [
        {"name": "puriq"}, {"args": {"x": 1}}, {"args": {"x": 0.0}},
        {"args": {"x": 0, "__proto__": {"changed": True}}},
        {"expected_client_id": "other_operator"}])
    def test_different_expected_request_or_operator_is_rejected(self, expected):
        out = self.invoke()
        self.verify(out)
        with pytest.raises(ValueError):
            self.verify(out, **expected)

    def test_wrong_trusted_key_and_unsigned_response_are_rejected(self):
        out = self.invoke()
        other = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        with pytest.raises(ValueError):
            self.verify(out, trusted_public_key_pem=other)
        out["dsse"]["signatures"] = []
        with pytest.raises(ValueError):
            self.verify(out)

    def test_signed_payload_and_outer_receipt_mutation_are_rejected(self):
        out = self.invoke()
        altered = copy.deepcopy(out)
        packet = json.loads(base64.b64decode(altered["dsse"]["payload"]))
        packet["receipt"]["status"] = "failure"
        altered["dsse"]["payload"] = base64.b64encode(canonical_bytes(packet)).decode()
        with pytest.raises(ValueError):
            self.verify(altered)
        for field in ("receipt_id", "continuum_hash", "prev_hash", "puriq_score"):
            altered = copy.deepcopy(out)
            altered["khipu_receipt"][field] = "altered"
            with pytest.raises(ValueError):
                self.verify(altered)

    def test_missing_binding_is_not_accepted_as_legacy_success(self):
        out = self.invoke()
        signed = json.loads(base64.b64decode(out["dsse"]["payload"]))
        signed["receipt"]["detail"].pop("formula_call_binding", None)
        digest = hashlib.sha256(canonical_bytes(signed["receipt"])).hexdigest()
        signed["continuum_hash"] = digest
        out["khipu_receipt"]["continuum_hash"] = digest
        out["dsse"] = S.SIGNER.sign(signed)
        with pytest.raises(ValueError):
            self.verify(out)

    def test_decline_binds_request_and_null_result_without_backend_call(self, monkeypatch):
        called = []
        async def backend(*_):
            called.append(True)
            raise AssertionError("must not call")
        monkeypatch.setattr(S.B, "formula_evaluate", backend)
        S._ctx_client.set(None)
        out = self.invoke(receipt_challenge=CHALLENGE)
        assert out["status"] == "declined" and out["data"] is None and called == []
        self.verify(out, expected_client_id="anonymous", receipt_challenge=CHALLENGE)

    def test_nonfinite_result_becomes_bound_failure(self, monkeypatch):
        async def backend(*_):
            return {"deployed": True, "http_status": 200, "error": None,
                    "data": {"value": float("nan")}}
        monkeypatch.setattr(S.B, "formula_evaluate", backend)
        out = self.invoke()
        assert out["status"] == "failure" and out["data"] is None
        self.verify(out)

    def test_nonfinite_or_lossy_input_rejected_before_backend_construction(self, monkeypatch):
        from unittest.mock import Mock
        backend = Mock(side_effect=AssertionError("must not construct backend"))
        monkeypatch.setattr(S.B, "formula_evaluate", backend)
        for args in ({"x": float("nan")}, {"x": float("inf")}, {1: "lost key"},
                     {"x": (1, 2)}):
            with pytest.raises(ValueError):
                asyncio.run(S.szl_formula_evaluate(name="sigmoid", args=args))
        backend.assert_not_called()

    def test_invalid_challenge_rejected_before_backend_construction(self, monkeypatch):
        from unittest.mock import Mock
        backend = Mock(side_effect=AssertionError("must not construct backend"))
        monkeypatch.setattr(S.B, "formula_evaluate", backend)
        for challenge in ("", "short", "x" * 129, "x" * 22 + "\n", "é" * 22):
            with pytest.raises(ValueError):
                self.invoke(receipt_challenge=challenge)
        backend.assert_not_called()

    def test_effective_default_args_and_json_order_have_stable_binding(self):
        assert formula_request("sigmoid", None, None) == formula_request("sigmoid", {}, None)
        assert canonical_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
        assert canonical_bytes({"__proto__": None, "é": 1.0}) == b'{"__proto__":null,"\\u00e9":1.0}'
        assert canonical_bytes(-0.0) == b'-0.0'

    def test_backend_cannot_rewrite_bound_request_by_mutating_args(self, monkeypatch):
        async def backend(_, args):
            args["x"] = 100
            return {"deployed": True, "http_status": 200, "error": None,
                    "data": {"value": "fixture: backend mutated its argument copy"}}
        monkeypatch.setattr(S.B, "formula_evaluate", backend)
        self.verify(self.invoke())

    def test_real_http_call_carries_challenge_and_retains_operator_admission(self, monkeypatch):
        from starlette.testclient import TestClient
        from hatun_mcp import server_http as http
        for var in list(os.environ):
            if var.startswith("HATUN_MCP_SCOPE_"):
                monkeypatch.delenv(var)
        key = "szl_formula_binding_fixture"
        fingerprint = hashlib.pbkdf2_hmac(
            "sha256", key.encode(), http._FP_SALT, http._FP_ITERATIONS).hex()[:16]
        monkeypatch.setenv("HATUN_MCP_SCOPE_" + fingerprint, "read")
        headers = {"authorization": "Bearer " + key,
                   "accept": "application/json, text/event-stream"}
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "szl_formula_evaluate", "arguments": {
                "name": "sigmoid", "args": {"x": 0}, "receipt_challenge": CHALLENGE}}}
        with TestClient(http.app, base_url=http.PUBLIC_BASE) as client:
            assert client.post("/mcp/", json=request).status_code == 401
            result = client.post("/mcp/", headers=headers, json=request)
            assert result.status_code == 200
            out = json.loads(result.json()["result"]["content"][0]["text"])
            self.verify(out, expected_client_id="client_" + fingerprint,
                        receipt_challenge=CHALLENGE)
            request["params"]["name"] = "dsse_sign"
            assert client.post("/mcp/", headers=headers, json=request).status_code == 403

    def test_signed_duplicate_json_fields_are_rejected(self):
        from cryptography.hazmat.primitives import hashes
        out = self.invoke()
        env = out["dsse"]
        raw = base64.b64decode(env["payload"])
        raw = b'{"receipt":null,' + raw[1:]
        payload_type = env["payloadType"].encode()
        pae = (b"DSSEv1 " + str(len(payload_type)).encode() + b" " + payload_type
               + b" " + str(len(raw)).encode() + b" " + raw)
        env["payload"] = base64.b64encode(raw).decode()
        env["signatures"][0]["sig"] = base64.b64encode(
            S.SIGNER._key.sign(pae, ec.ECDSA(hashes.SHA256()))).decode()
        with pytest.raises(ValueError):
            self.verify(out)

    def test_published_cross_implementation_vectors(self):
        from hatun_mcp.formula_receipts import bind_formula_call
        vectors = json.loads((Path(__file__).parent / "fixtures/formula-call-binding-v1.json").read_text())
        assert len(vectors) == 3
        for vector in vectors:
            assert canonical_bytes(vector["request"]).decode() == vector["request_canonical_utf8"]
            assert canonical_bytes(vector["response"]).decode() == vector["response_canonical_utf8"]
            assert bind_formula_call(vector["request"], vector["response"]) == vector["binding"]

    @pytest.mark.parametrize("field,value", [("tool", "other_tool"),
        ("operation_id", "other.operation"), ("client_id", "other_operator")])
    def test_validly_signed_wrong_operation_or_identity_is_rejected(self, field, value):
        out = self.invoke()
        signed = json.loads(base64.b64decode(out["dsse"]["payload"]))
        signed["receipt"][field] = value
        digest = hashlib.sha256(canonical_bytes(signed["receipt"])).hexdigest()
        signed["continuum_hash"] = digest
        out["khipu_receipt"]["continuum_hash"] = digest
        out["dsse"] = S.SIGNER.sign(signed)
        with pytest.raises(ValueError):
            self.verify(out)
