"""Hermetic operator-key and read-only HTTP transport admission regressions."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("HATUN_MCP_DISABLE_DYNAMIC", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starlette.testclient import TestClient  # noqa: E402
from hatun_mcp import server_http as http  # noqa: E402

KEY = "szl_test_admitted_http"


def bind(key=KEY, scope="read"):
    fingerprint = hashlib.pbkdf2_hmac(
        "sha256", key.encode(), http._FP_SALT, http._FP_ITERATIONS,
    ).hex()[:16]
    name = "HATUN_MCP_SCOPE_" + fingerprint
    os.environ[name] = scope
    return name


def rpc(method, params=None):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


class HttpAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ)
        self.environment.start()
        for name in list(os.environ):
            if name.startswith("HATUN_MCP_SCOPE_"):
                os.environ.pop(name)
        self.client = TestClient(http.app, base_url=http.PUBLIC_BASE)
        self.headers = {"authorization": "Bearer " + KEY,
                        "accept": "application/json, text/event-stream"}

    def tearDown(self):
        self.client.close()
        self.environment.stop()

    def test_prefix_is_not_admission_and_only_explicit_valid_scopes_resolve(self):
        self.assertIsNone(http.resolve_api_key(KEY)[0])
        for scope in ("", "READ", " read", "owner", "false"):
            with self.subTest(scope=scope):
                bind(scope=scope)
                self.assertIsNone(http.resolve_api_key(KEY)[0])
                self.assertFalse(http.http_auth_configured())
        for scope in ("read", "write", "admin"):
            with self.subTest(scope=scope):
                binding = bind(scope=scope)
                identity, actual_scope = http.resolve_api_key(KEY)
                self.assertEqual(identity, "client_" + binding.removeprefix("HATUN_MCP_SCOPE_"))
                self.assertEqual(actual_scope, scope)
                self.assertTrue(http.http_auth_configured())
                os.environ.pop(binding)
                self.assertIsNone(http.resolve_api_key(KEY)[0])

    def test_unbounded_or_malformed_keys_never_run_the_kdf(self):
        with patch.object(http.hashlib, "pbkdf2_hmac") as kdf:
            for key in (None, "", "plain", "szl_", "szl_" + "x" * 253,
                        "szl_secret value", "szl_key\n", "szl_\N{LATIN SMALL LETTER E WITH ACUTE}"):
                with self.subTest(length=len(key) if key else 0):
                    self.assertIsNone(http.resolve_api_key(key)[0])
            kdf.assert_not_called()

    def test_all_transport_aliases_reject_anonymous_and_forged_prefix(self):
        bind()
        before = http.KHIPU.depth()
        for path in ("/mcp", "/mcp/", "/sse", "/sse/", "/messages", "/messages/", "/sse/messages/"):
            for headers in ({}, {"authorization": "Bearer szl_forged_unissued"}):
                with self.subTest(path=path, has_header=bool(headers)):
                    for response in (self.client.get(path, headers=headers),
                                     self.client.post(path, headers=headers, json=rpc("initialize"))):
                        self.assertEqual(response.status_code, 401)
                        self.assertIn("Bearer", response.headers["www-authenticate"])
                        self.assertNotIn("szl_forged", response.text)
        self.assertEqual(http.KHIPU.depth(), before)

    def test_anonymous_override_and_claimed_approval_do_not_admit_a_key(self):
        os.environ["HATUN_MCP_ALLOW_ANON"] = "true"
        response = self.client.post("/mcp/", headers={
            "authorization": "Bearer szl_forged_unissued",
            "x-second-approver": "claimed-approver", "x-sovereign-mode": "true",
        }, json=rpc("tools/call", {"name": "dsse_sign", "arguments": {"payload": {}}}))
        self.assertEqual(response.status_code, 401)
        self.assertTrue(http._server_card()["authentication"]["required"])

    def test_duplicate_or_conflicting_credentials_fail_closed(self):
        bind()
        candidates = [
            [("authorization", "Bearer " + KEY), ("x-api-key", KEY)],
            [("authorization", "Bearer " + KEY), ("authorization", "Bearer " + KEY)],
            [("x-api-key", KEY), ("x-api-key", KEY)],
            [("authorization", "Basic invalid"), ("x-api-key", KEY)],
        ]
        for headers in candidates:
            with self.subTest(header_names=[h[0] for h in headers]):
                response = self.client.post("/mcp/", headers=headers, json=rpc("initialize"))
                self.assertEqual(response.status_code, 401)

    def test_read_write_and_admin_bindings_cannot_call_privileged_or_dynamic_tools(self):
        names = ("dsse_sign", "khipu_append_and_verify", "puriq_master_tool",
                 "szl_killinchu_cue", "szl_lambda_quorum", "szl_puriq_evaluate",
                 "yuyay_gate_check", "mesh_quorum_status", "governance_pacbayes_bound",
                 "unreviewed_dynamic_tool")
        before = http.KHIPU.depth()
        for scope in ("read", "write", "admin"):
            bind(scope=scope)
            for path in ("/mcp", "/mcp/"):
                for name in names:
                    with self.subTest(scope=scope, path=path, tool=name):
                        response = self.client.post(path, headers={**self.headers,
                            "x-second-approver": "another-client", "x-sovereign-mode": "true",
                        }, json=rpc("tools/call", {"name": name, "arguments": {
                            "payload": {"marker": "must-not-execute"},
                            "context": {"two_person": True, "state_changing": False},
                        }}))
                        self.assertEqual(response.status_code, 403)
                        self.assertEqual(response.json()["error"], "tool_not_admitted_for_http")
        self.assertEqual(http.KHIPU.depth(), before)

    def test_admitted_keys_cannot_start_or_post_to_legacy_sessions(self):
        bind()
        before = http.KHIPU.depth()
        for path in ("/sse", "/sse/", "/messages", "/messages/", "/sse/messages/"):
            for response in (self.client.get(path, headers=self.headers),
                             self.client.post(path, headers=self.headers, json=rpc("initialize"))):
                self.assertEqual(response.status_code, 410)
                self.assertEqual(response.json()["error"], "legacy_transport_disabled")
        self.assertEqual(http.KHIPU.depth(), before)
        self.assertIsNone(self.client.get("/connect").json()["sse_endpoint"])

    def test_formula_fallback_and_global_receipt_resource_are_not_admitted(self):
        bind()
        for name in ("unknown_remote_formula", "kl_divergence", "kl", "pi", "master"):
            response = self.client.post("/mcp/", headers=self.headers, json=rpc(
                "tools/call", {"name": "szl_formula_evaluate", "arguments": {"name": name}},
            ))
            self.assertEqual(response.status_code, 403)
        response = self.client.post("/mcp/", headers=self.headers, json=rpc(
            "resources/read", {"uri": "hatun://khipu/recent"},
        ))
        self.assertEqual(response.status_code, 403)

    def test_invalid_batch_and_unknown_rpc_cannot_reach_dispatch(self):
        bind()
        for body in ([], [rpc("initialize")], {},
                     rpc("tools/call", {"name": []}), rpc("prompts/get", {"name": "dynamic"}),
                     rpc("tools/call", {"name": "szl_yuyay_score", "arguments": []})):
            response = self.client.post("/mcp/", headers=self.headers, json=body)
            self.assertIn(response.status_code, {400, 403})
        response = self.client.post("/mcp/", headers=self.headers, content="not JSON")
        self.assertEqual(response.status_code, 415)

    def test_streamed_body_limit_stops_before_downstream_execution(self):
        bind()
        dispatched = []
        sent = []
        chunks = iter((
            {"type": "http.request", "body": b"x" * http._MAX_RPC_BYTES, "more_body": True},
            {"type": "http.request", "body": b"x", "more_body": True},
        ))

        async def receive():
            return next(chunks)

        async def send(event):
            sent.append(event)

        async def downstream(*args):
            dispatched.append(True)

        scope = {"type": "http", "method": "POST", "path": "/mcp/", "headers": [
            (b"authorization", ("Bearer " + KEY).encode()), (b"content-type", b"application/json"),
        ]}
        asyncio.run(http.GovernanceAuthMiddleware(downstream)(scope, receive, send))
        self.assertFalse(dispatched)
        self.assertEqual(sent[0]["status"], 413)

    def test_slow_body_deadline_stops_before_downstream_execution(self):
        bind()
        dispatched, sent = [], []

        async def receive():
            await asyncio.Event().wait()

        async def send(event):
            sent.append(event)

        async def downstream(*args):
            dispatched.append(True)

        scope = {"type": "http", "method": "POST", "path": "/mcp/", "headers": [
            (b"authorization", ("Bearer " + KEY).encode()), (b"content-type", b"application/json"),
        ]}
        with patch.object(http, "_BODY_TIMEOUT_SECONDS", 0.01):
            asyncio.run(http.GovernanceAuthMiddleware(downstream)(scope, receive, send))
        self.assertFalse(dispatched)
        self.assertEqual(sent[0]["status"], 408)
        self.assertEqual(json.loads(sent[1]["body"])["error"], "mcp_body_timeout")

    def test_public_discovery_and_health_do_not_require_or_process_credentials(self):
        with patch.object(http.hashlib, "pbkdf2_hmac") as kdf:
            for path in ("/", "/healthz", "/connect", "/.well-known/mcp", "/api/console-state"):
                response = self.client.get(path, headers={"authorization": "Bearer szl_unissued"})
                self.assertEqual(response.status_code, 200)
            kdf.assert_not_called()
        descriptor = self.client.get("/connect").json()
        self.assertEqual(descriptor["http_transport_policy"]["profile"], "operator-read-only")
        self.assertEqual(descriptor["http_transport_policy"]["portal_validation"], "NOT_IMPLEMENTED")

    def test_http_readiness_requires_authentication_configuration(self):
        with patch.object(http, "SIGNER", SimpleNamespace(mode="ECDSA-P256")):
            response = self.client.get("/readyz")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["checks"]["authentication"], "UNAVAILABLE")
            self.assertEqual(self.client.get("/api/console-state").json()["health"]["readiness"], "NOT-READY")
            bind()
            response = self.client.get("/readyz")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["checks"]["authentication"], "CONFIGURED")

    def test_real_mcp_protocol_accepts_only_bound_read_calls(self):
        env = dict(os.environ, HATUN_MCP_DISABLE_DYNAMIC="true", HATUN_MCP_ALLOW_ANON="true")
        for name in ("HATUN_MCP_SIGNING_KEY", "HATUN_MCP_SIGNING_KEY_PATH", "SZL_RECEIPT_SINK"):
            env.pop(name, None)
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--protocol-check"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REAL MCP ADMISSION CHECKS PASSED", result.stdout)


def _protocol_check():
    for name in list(os.environ):
        if name.startswith("HATUN_MCP_SCOPE_"):
            os.environ.pop(name)
    binding = bind()
    headers = {"authorization": "Bearer " + KEY, "accept": "application/json, text/event-stream"}
    initialize = rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                  "clientInfo": {"name": "admission-test", "version": "1"}})
    with TestClient(http.app, base_url=http.PUBLIC_BASE) as client:
        assert client.post("/mcp/", json=initialize).status_code == 401
        assert client.post("/mcp/", headers={**headers, "authorization": "Bearer szl_unissued"},
                           json=initialize).status_code == 401
        assert client.post("/mcp/", headers=headers, json=initialize).status_code == 200
        listed = client.post("/mcp/", headers=headers, json=rpc("tools/list"))
        assert listed.status_code == 200
        request = rpc("tools/call", {"name": "szl_formula_evaluate",
                                     "arguments": {"name": "sigmoid", "args": {"x": 0}}})
        response = client.post("/mcp/", headers={**headers, "x-sovereign-mode": "true",
                                               "x-second-approver": "forged"}, json=request)
        assert response.status_code == 200, response.text
        body = json.loads(response.json()["result"]["content"][0]["text"])
        assert body["status"] == "success", body
        assert body["data"]["value"] == 0.5
        assert body["governance"]["sovereign_mode"] is False
        assert http.KHIPU.recent(1)[0]["client_id"] == "client_" + binding.removeprefix("HATUN_MCP_SCOPE_")
        assert http._ctx_client.get() is None
        assert http._ctx_second_approver.get() is None
        assert http._ctx_sovereign.get() is False
        assert client.post("/mcp/", headers=headers, json=rpc("tools/call", {
            "name": "dsse_sign", "arguments": {"payload": {"must": "not sign"}},
        })).status_code == 403
        os.environ.pop(binding)
        assert client.post("/mcp/", headers=headers, json=request).status_code == 401
        bind()
        api_headers = {"x-api-key": KEY, "accept": headers["accept"]}
        assert client.post("/mcp/", headers=api_headers, json=request).status_code == 200
    print("REAL MCP ADMISSION CHECKS PASSED")


if __name__ == "__main__":
    if "--protocol-check" in sys.argv:
        _protocol_check()
    else:
        unittest.main()
