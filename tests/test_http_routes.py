"""HTTP-route tests for the landing-page CTA targets.

These lock the three landing-page buttons to real, resolving targets so a
regression (a renamed route, a dropped alias, a /mcp -> http:// downgrade)
fails CI instead of shipping a dead button to the Space:

  * "Inspect the server card" -> the canonical card and every short alias
    return 200 with the real server-card JSON (not a 404 / not a stub).
  * "Source on GitHub" -> the console links the real public repo.
  * "Connect an agent" -> the connect descriptor and the in-page config
    snippet point at the trailing-slash /mcp/ endpoint, not the bare /mcp
    that 307-redirects (and downgrades to http:// behind the HF proxy).

Run hermetically (no organ network): HATUN_MCP_DISABLE_DYNAMIC=true.
SPDX-License-Identifier: Apache-2.0
"""
import base64
import hashlib
import json
import os
import subprocess
import sys

import pytest

os.environ.setdefault("HATUN_MCP_DISABLE_DYNAMIC", "true")
os.environ.setdefault("HATUN_MCP_BACKEND_TIMEOUT", "1.0")

from cryptography.hazmat.primitives.asymmetric import ec, rsa  # noqa: E402
from cryptography.hazmat.primitives.serialization import (  # noqa: E402
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from starlette.testclient import TestClient  # noqa: E402

from hatun_mcp import server_http  # noqa: E402
from hatun_mcp.console import CONSOLE_HTML  # noqa: E402
from hatun_mcp.governance import DsseSigner  # noqa: E402
from hatun_mcp.deployment import public_base  # noqa: E402

BASE = server_http.PUBLIC_BASE
REPO = "https://github.com/szl-holdings/hatun-mcp"
ATTESTATION_PATH = "/.well-known/mcp-manifest-attestation"


@pytest.fixture
def auth_binding(monkeypatch):
    # Hermetic registration store and fast fixture KDF; production cost stays intact.
    for name in tuple(os.environ):
        if name.startswith("HATUN_MCP_SCOPE_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(server_http, "_FP_ITERATIONS", 1)

    def bind(key, scope):
        fingerprint = hashlib.pbkdf2_hmac(
            "sha256", key.encode(), server_http._FP_SALT, server_http._FP_ITERATIONS,
        ).hex()[:16]
        monkeypatch.setenv(f"HATUN_MCP_SCOPE_{fingerprint}", scope)
        return f"client_{fingerprint}"
    return bind


@pytest.mark.parametrize("key", [None, "", "not-an-szl-key", "szl_", "szl_unregistered_fixture"])
def test_auth_binding_rejects_missing_or_unregistered_key(auth_binding, key):
    assert server_http.resolve_api_key(key) == (None, "read")


@pytest.mark.parametrize("scope", ["", "unknown", "READ", " read", "admin "])
def test_auth_binding_rejects_invalid_registered_scope(auth_binding, scope):
    key = "szl_registered_fixture"
    auth_binding(key, scope)
    assert server_http.resolve_api_key(key) == (None, "read")


@pytest.mark.parametrize("scope", ["read", "write", "admin"])
def test_auth_binding_preserves_explicit_registered_scope(auth_binding, scope):
    key = "szl_registered_fixture"
    expected_client = auth_binding(key, scope)
    assert server_http.resolve_api_key(key) == (expected_client, scope)


@pytest.mark.parametrize("header", ["Authorization", "X-Api-Key"])
@pytest.mark.parametrize("registered,allow_anonymous", [(False, False), (True, False), (False, True)])
def test_auth_binding_controls_backend_admission(auth_binding, monkeypatch, header, registered, allow_anonymous):
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from hatun_mcp import server as server
    from hatun_mcp.governance import ClientRegistry, KhipuChain

    monkeypatch.setattr(server, "ALLOW_ANON", allow_anonymous)
    monkeypatch.setattr(server, "KHIPU", KhipuChain())
    monkeypatch.setattr(server, "CLIENTS", ClientRegistry())
    calls = []

    async def backend():
        calls.append(True)
        return {"deployed": True, "error": None, "data": {"fixture": True}}

    async def invoke(request):
        result = await server.governed(
            tool="auth_binding_fixture", operation_id="fixture.read", gate_text="read a test record",
            needs_scope="read", backend_coro=backend(),
        )
        return JSONResponse(result)

    app = Starlette(routes=[Route("/invoke", invoke)])
    app.add_middleware(server_http.GovernanceAuthMiddleware)
    key = "szl_auth_boundary_fixture"
    if registered:
        auth_binding(key, "read")
    value = f"Bearer {key}" if header == "Authorization" else key
    result = TestClient(app).get("/invoke", headers={header: value}).json()
    if registered or allow_anonymous:
        assert result["status"] == "success"
        assert calls == [True]
    else:
        assert result["status"] == "declined"
        assert result["gate_transparency"]["reason"] == "no_api_key"
        assert calls == []
    assert result["khipu_receipt"]["chain_verified"] is True


def test_auth_binding_does_not_hide_public_read_only_routes(auth_binding):
    public = TestClient(server_http.app, base_url=BASE)
    for path in ("/healthz", "/connect", "/.well-known/mcp"):
        response = public.get(path, headers={"Authorization": "Bearer szl_unregistered_fixture"})
        assert response.status_code == 200

client = TestClient(server_http.app, base_url=BASE)


@pytest.mark.parametrize("origin", [
    "https://gateway.example.org",
    "https://gateway.example.org:8443",
    "http://127.0.0.1:7860",
    "http://localhost:7860",
    "http://[::1]:7860",
])
def test_public_origin_accepts_https_or_local_development(origin):
    assert public_base(origin) == origin
    assert public_base(origin + "/") == origin


def test_public_origin_normalizes_to_browser_origin():
    assert public_base("https://GATEWAY.example.org:443/") == "https://gateway.example.org"
    assert public_base("http://LOCALHOST:80/") == "http://localhost"
    assert public_base("http://[0:0:0:0:0:0:0:1]:7860") == "http://[::1]:7860"
    assert public_base("https://[2001:0DB8:0:0:0:0:0:1]:443/") == "https://[2001:db8::1]"


@pytest.mark.parametrize("origin", [
    "", "/relative", "ftp://gateway.example.org", "http://gateway.example.org",
    "https://user:private@gateway.example.org", "https://gateway.example.org/mcp",
    "https://gateway.example.org?token=private", "https://gateway.example.org#fragment",
    "https://gateway.example.org?", "https://gateway.example.org#",
    "https://gateway.example.org:\n443", "https://gateway.example.org:invalid",
    "https://gateway.example.org:70000", "https://gateway.example.org:0",
    "https://gateway.example.org:", "https://gateway.example.org\\evil",
    "https://gateway.example.org/<script>", "https://gateway%2Fexample.org",
    "https://gateway..example.org", "https://-gateway.example.org",
    "https://gateway.example-.org", "http://[::1%25eth0]:7860",
    "https://2130706433", "https://127.000.000.001", "https://0x7f000001",
    "https://999.999.999.999", "https://[v1.example]",
    "https://0x", "https://1.0x",
])
def test_public_origin_rejects_unsafe_or_misleading_endpoints(origin):
    with pytest.raises(ValueError, match="HATUN_MCP_PUBLIC_BASE") as error:
        public_base(origin)
    assert "private" not in str(error.value)


@pytest.mark.parametrize(("configured", "expected"), [
    (None, "http://127.0.0.1:7860"),
    ("https://gateway.example.org:8443/", "https://gateway.example.org:8443"),
    ("http://[0:0:0:0:0:0:0:1]:7860", "http://[::1]:7860"),
])
def test_fresh_runtime_binds_all_discovery_to_operator_origin(configured, expected):
    env = os.environ.copy()
    for key in ("HATUN_MCP_PUBLIC_BASE", "HATUN_MCP_ALLOWED_ORIGINS",
                "HATUN_MCP_ALLOWED_HOSTS", "HATUN_MCP_SIGNING_KEY"):
        env.pop(key, None)
    env["HATUN_MCP_DISABLE_DYNAMIC"] = "true"
    if configured is not None:
        env["HATUN_MCP_PUBLIC_BASE"] = configured
    code = r'''
import hashlib, json
from starlette.testclient import TestClient
from hatun_mcp import server_http as server
from hatun_mcp.console import CONSOLE_HTML, SPACE_URL
client = TestClient(server.app, base_url="https://untrusted.example.org")
connect = client.get("/connect", headers={"X-Forwarded-Host": "attacker.example.org"}).json()
manifest = client.get("/.well-known/mcp").content
attestation = client.get("/.well-known/mcp-manifest-attestation").json()
initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-03-26", "capabilities": {},
    "clientInfo": {"name": "deployment-contract-test", "version": "1"},
}}
headers = {"accept": "application/json, text/event-stream", "origin": server.PUBLIC_BASE}
with TestClient(server.app, base_url=server.PUBLIC_BASE) as runtime:
    handshake = runtime.post("/mcp/", headers=headers, json=initialize)
    wrong_host = runtime.post("/mcp/", headers={**headers, "host": "attacker.example.org"}, json=initialize)
    wrong_origin = runtime.post("/mcp/", headers={**headers, "origin": "https://attacker.example.org"}, json=initialize)
print(json.dumps({
    "base": server.PUBLIC_BASE,
    "console_base": SPACE_URL,
    "origin_allowed": server.PUBLIC_BASE in server.ALLOWED_ORIGINS,
    "connect": connect,
    "manifest_uri": attestation["manifest"]["uri"],
    "subject_uri": attestation["statement"]["subject"][0]["name"],
    "digest_matches": attestation["manifest"]["digest"]["sha256"] == hashlib.sha256(manifest).hexdigest(),
    "console_endpoint": server.PUBLIC_BASE + "/mcp/" in CONSOLE_HTML,
    "retired_host": "szlholdings-hatun-mcp.hf.space" in CONSOLE_HTML + json.dumps(connect) + json.dumps(attestation),
    "handshake_status": handshake.status_code,
    "handshake_server": handshake.json().get("result", {}).get("serverInfo", {}).get("name"),
    "wrong_host_status": wrong_host.status_code,
    "wrong_origin_status": wrong_origin.status_code,
}))
'''
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, text=True,
        capture_output=True, check=True, timeout=30,
    )
    observed = json.loads(result.stdout)
    assert observed["base"] == observed["console_base"] == expected
    assert observed["origin_allowed"] is True
    assert observed["connect"]["mcp_endpoint"] == expected + "/mcp/"
    assert observed["connect"]["sse_endpoint"] == expected + "/sse/"
    assert observed["connect"]["server_card"] == expected + "/.well-known/mcp/server-card.json"
    assert observed["manifest_uri"] == observed["subject_uri"] == expected + "/.well-known/mcp"
    assert observed["digest_matches"] is True
    assert observed["console_endpoint"] is True
    assert observed["retired_host"] is False
    assert observed["handshake_status"] == 200
    assert observed["handshake_server"] == "hatun-mcp"
    assert observed["wrong_host_status"] == 421
    assert observed["wrong_origin_status"] == 403

# Every path a human or registry might poke for "the server card".
CARD_PATHS = [
    "/.well-known/mcp/server-card.json",
    "/.well-known/mcp",
    "/.well-known/mcp/",
    "/server-card",
    "/card",
]


def test_server_card_and_aliases_serve_real_card():
    exact_bodies = []
    for path in CARD_PATHS:
        r = client.get(path, headers={"accept": "application/json"},
                       follow_redirects=False)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        exact_bodies.append(r.content)
        body = r.json()
        # Real card: actual server metadata + the server's actual tools.
        assert body["serverInfo"]["name"] == "hatun-mcp"
        assert len(body["tools"]) >= 1
        assert "governance" in body
        assert body["authentication"]["schemes"] == ["apiKey"]
    assert all(body == exact_bodies[0] for body in exact_bodies)


def test_manifest_attestation_binds_exact_cached_card_bytes():
    manifest = client.get("/.well-known/mcp").content
    first = client.get(ATTESTATION_PATH, headers={"accept": "application/json"})
    second = client.get(
        f"{ATTESTATION_PATH}?payload=caller-controlled",
        headers={"accept": "application/json"},
    )

    assert first.status_code == 200
    assert first.content == second.content
    assert first.headers["content-type"].startswith("application/json")
    assert first.headers["cache-control"] == "no-store"
    assert first.headers["access-control-allow-origin"] == "*"

    body = first.json()
    digest = hashlib.sha256(manifest).hexdigest()
    statement = body["statement"]
    predicate = statement["predicate"]
    source_revision = predicate["producer"]["sourceRevision"]

    assert body["schemaVersion"] == "1.0"
    assert body["manifest"] == {
        "uri": f"{BASE}/.well-known/mcp",
        "mediaType": "application/json",
        "byteLength": len(manifest),
        "digest": {"sha256": digest},
    }
    assert statement["_type"] == "https://in-toto.io/Statement/v1"
    assert statement["subject"] == [
        {
            "name": f"{BASE}/.well-known/mcp",
            "digest": {"sha256": digest},
        }
    ]
    assert statement["predicateType"] == (
        "https://szlholdings.com/attestations/mcp-manifest/v1"
    )
    assert predicate["manifest"]["byteLength"] == len(manifest)
    assert predicate["scope"] == {
        "integrity": "EXACT_BYTES",
        "runtimeToolParity": "NOT_ATTESTED",
        "mcpServerCardSpecification": "DRAFT_EXTENSION",
    }
    assert source_revision["state"] in {"OBSERVED", "UNAVAILABLE"}
    if source_revision["state"] == "OBSERVED":
        assert len(source_revision["value"]) == 40
        assert all(
            character in "0123456789abcdef"
            for character in source_revision["value"]
        )
    else:
        assert source_revision["value"] is None
    assert body["receiptMinted"] is False

    if body["signing"]["state"] == "SIGNED":
        envelope = body["dsseEnvelope"]
        assert set(envelope) == {"payloadType", "payload", "signatures"}
        assert envelope["payloadType"] == "application/vnd.in-toto+json"
        assert json.loads(
            base64.b64decode(envelope["payload"], validate=True)
        ) == statement
        assert len(envelope["signatures"]) == 1
        assert envelope["signatures"][0]["keyid"] == "szlholdings-ec-p256"
        assert body["signing"]["signerMode"] == "ECDSA-P256"
        assert body["signing"]["publicKey"] == f"{BASE}/pubkey"
        assert predicate["attestation"]["algorithm"] == "ECDSA-P256"
    else:
        assert body["signing"] == {
            "state": "UNSIGNED",
            "signerMode": "PLACEHOLDER",
            "keyid": None,
            "publicKey": None,
            "transparencyLog": "UNAVAILABLE",
        }
        assert body["dsseEnvelope"] is None
        assert predicate["attestation"]["algorithm"] is None


def test_manifest_attestation_detects_one_byte_manifest_change():
    manifest = client.get("/.well-known/mcp").content
    attested_digest = client.get(ATTESTATION_PATH).json()["manifest"]["digest"][
        "sha256"
    ]
    tampered = manifest[:-1] + bytes([manifest[-1] ^ 1])

    assert hashlib.sha256(manifest).hexdigest() == attested_digest
    assert hashlib.sha256(tampered).hexdigest() != attested_digest


def test_manifest_attestation_is_get_only_and_not_a_signing_oracle():
    baseline = client.get(ATTESTATION_PATH).content
    response = client.post(
        ATTESTATION_PATH,
        json={"statement": {"subject": [{"name": "caller-controlled"}]}},
    )

    assert response.status_code == 405
    assert client.get(ATTESTATION_PATH).content == baseline


def test_manifest_attestation_builder_uses_existing_real_signer(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setenv(
        "HATUN_MCP_SIGNING_KEY",
        key.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption(),
        ).decode(),
    )
    signer = DsseSigner()
    card = b'{"serverInfo":{"name":"hatun-mcp"}}'

    body = server_http._build_manifest_attestation(
        manifest_bytes=card,
        signer=signer,
        source_revision="A" * 40,
    )

    assert body["signing"]["state"] == "SIGNED"
    assert body["signing"]["signerMode"] == "ECDSA-P256"
    assert body["dsseEnvelope"]["payloadType"] == "application/vnd.in-toto+json"
    assert json.loads(
        base64.b64decode(body["dsseEnvelope"]["payload"], validate=True)
    ) == body["statement"]
    assert body["statement"]["predicate"]["producer"]["sourceRevision"] == {
        "state": "OBSERVED",
        "value": "a" * 40,
    }


def test_no_card_path_404s():
    for path in CARD_PATHS:
        r = client.get(path, headers={"accept": "application/json"},
                       follow_redirects=False)
        assert r.status_code != 404, f"{path} regressed to 404"


def test_connect_descriptor_points_at_trailing_slash_mcp():
    r = client.get("/connect", headers={"accept": "application/json"})
    assert r.status_code == 200
    info = r.json()
    # Must be the trailing-slash endpoint (the bare /mcp 307-redirects and the
    # Location downgrades to http:// behind the HF reverse proxy).
    assert info["mcp_endpoint"] == f"{BASE}/mcp/"
    assert info["mcp_endpoint"].endswith("/mcp/")
    assert info["docs"] == REPO
    assert info["manifest_attestation"] == f"{BASE}{ATTESTATION_PATH}"


def test_index_json_advertises_trailing_slash_mcp():
    r = client.get("/", headers={"accept": "application/json"})
    assert r.status_code == 200
    j = r.json()
    assert j["mcp_endpoint"] == "/mcp/"
    assert j["manifest_attestation"] == ATTESTATION_PATH
    assert j["connect"] == "/connect"
    assert j["readyz"] == "/readyz"
    assert j["docs"] == REPO


def test_healthz_and_pubkey_resolve():
    assert client.get("/healthz").status_code == 200
    assert client.get("/pubkey").status_code == 200


def test_build_info_is_exact_source_bound(monkeypatch):
    revision = "a" * 40
    monkeypatch.setenv("SZL_GIT_SHA", revision)
    response = client.get("/api/build-info")
    body = response.json()
    assert response.status_code == 200
    assert body["build"] == {"state": "OBSERVED", "revision": revision}
    assert body["runtime"]["transport"] == "streamable-http"
    assert body["receipt_minted"] is False
    assert response.headers["cache-control"] == "no-store"


def test_build_info_fails_closed_without_exact_revision(monkeypatch):
    monkeypatch.setenv("SZL_GIT_SHA", "not-a-full-sha")
    response = client.get("/api/build-info")
    body = response.json()
    assert response.status_code == 503
    assert body["build"] == {"state": "UNAVAILABLE", "revision": None}
    assert body["receipt_minted"] is False


def test_readyz_separates_liveness_from_signed_release_readiness():
    response = client.get("/readyz")
    body = response.json()

    assert response.status_code == (200 if body["ready"] else 503)
    assert body["status"] == ("ready" if body["ready"] else "not_ready")
    assert body["checks"]["receipt_chain"] in {"VERIFIED", "FAILED"}
    assert body["checks"]["signer"] in {"CONFIGURED", "UNAVAILABLE"}
    assert response.headers["cache-control"] == "no-store"


def test_readyz_rejects_parseable_but_incompatible_signer(monkeypatch):
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = rsa_key.private_bytes(
        Encoding.PEM,
        PrivateFormat.PKCS8,
        NoEncryption(),
    ).decode()
    monkeypatch.setenv("HATUN_MCP_SIGNING_KEY", pem)
    incompatible_signer = DsseSigner()
    monkeypatch.setattr(server_http, "SIGNER", incompatible_signer)

    response = client.get("/readyz")
    body = response.json()

    assert response.status_code == 503
    assert body["ready"] is False
    assert body["checks"]["signer"] == "UNAVAILABLE"
    assert body["signer_mode"] == "PLACEHOLDER"


def test_console_source_button_links_real_repo():
    # "Source on GitHub" button + footer must link the real public repo.
    assert f'href="{REPO}"' in CONSOLE_HTML


def test_console_connect_snippet_uses_trailing_slash_mcp():
    # The in-page connect config must not steer clients at the bare /mcp.
    assert f"{BASE}/mcp/" in CONSOLE_HTML
    assert f'{BASE}/mcp"' not in CONSOLE_HTML
    assert f"{BASE}/mcp<" not in CONSOLE_HTML


def test_security_headers_on_every_route():
    # SAFE-NOW hardening (R2): real headers on the HTML console AND the JSON/health
    # routes. Hitting the browser console path (Accept: text/html) and a machine
    # route both carry the full set.
    for path, accept in (
        ("/", "text/html"),
        ("/healthz", "application/json"),
        ("/readyz", "application/json"),
    ):
        r = client.get(path, headers={"accept": accept})
        assert r.status_code in {200, 503}, path
        h = r.headers
        csp = h["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "object-src 'none'" in csp
        # legit HF embed allowed; not wide open
        assert "frame-ancestors 'self' https://huggingface.co https://*.hf.space" in csp
        assert h["x-content-type-options"] == "nosniff"
        assert h["referrer-policy"] == "strict-origin-when-cross-origin"
        assert h["strict-transport-security"].startswith("max-age=")
        # never X-Frame-Options: DENY (it would break the HF iframe embed)
        assert h.get("x-frame-options", "").upper() != "DENY"


def test_origin_allowlist_still_guards_mcp_transport():
    # Pre-existing DNS-rebinding defense must remain: an untrusted Origin on the
    # MCP transport path is rejected, the new header middleware doesn't bypass it.
    r = client.get("/mcp/", headers={"origin": "https://evil.example.com"})
    assert r.status_code == 403
    assert r.json()["error"] == "origin_not_allowed"
