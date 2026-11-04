"""
hatun_mcp.server_http — admitted read-only Streamable HTTP entrypoint (/mcp).

Wraps the FastMCP app in a Starlette application that:
  * authenticates each request via the SZL API key (Authorization: Bearer szl_... ,
    or X-Api-Key). Resolves key -> client_id + scope and sets the request contextvars.
  * validates the Origin header (DNS-rebinding defense; MCP transport requirement).
  * admits only explicit operator-bound credentials and reviewed read-only RPCs.
  * ignores caller-supplied sovereign-mode and second-approver claims.
  * serves the draft server-card discovery extension so registries can enumerate
    the 26 static tools even behind the auth wall.
  * binds the exact card bytes to a cached in-toto Statement v1 / DSSE artifact.
  * serves /healthz, /readyz, and /pubkey (DSSE verification key).

Run:  uvicorn hatun_mcp.server_http:app --host 0.0.0.0 --port 7860
SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route

from .deployment import PUBLIC_BASE
from . import server as _server
from .server import (
    SIGNER, CLIENTS, KHIPU, mcp,
    _ctx_client, _ctx_scope, _ctx_sovereign, _ctx_second_approver,
)
from .governance import (
    DOCTRINE,
    DSSE_KEY_ID,
    IN_TOTO_PAYLOAD_TYPE,
    IN_TOTO_STATEMENT_TYPE,
    DsseSigner,
)
from .console import CONSOLE_HTML
from .state import console_state, observed_signer_mode, set_card_tool_names

ALLOWED_ORIGINS = set(
    o.strip() for o in os.environ.get(
        "HATUN_MCP_ALLOWED_ORIGINS",
        f"{PUBLIC_BASE},https://smithery.ai,http://localhost",
    ).split(",")
)

MCP_MANIFEST_PATH = "/.well-known/mcp"
MCP_MANIFEST_URI = f"{PUBLIC_BASE}{MCP_MANIFEST_PATH}"
MCP_MANIFEST_ATTESTATION_PATH = "/.well-known/mcp-manifest-attestation"
MCP_MANIFEST_ATTESTATION_URI = f"{PUBLIC_BASE}{MCP_MANIFEST_ATTESTATION_PATH}"
MCP_MANIFEST_PREDICATE_TYPE = (
    "https://szlholdings.com/attestations/mcp-manifest/v1"
)
SOURCE_REPOSITORY = "https://github.com/szl-holdings/hatun-mcp"
_DISCOVERY_HEADERS = {
    "Cache-Control": "no-store",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET",
    "Access-Control-Allow-Headers": "Content-Type",
}

# Fixed domain-separation salt + iteration count for the API-key fingerprint KDF.
# The salt is a public, non-secret constant: it makes the fingerprint deterministic
# (so the same caller keeps a stable client_id / reputation) while forcing every
# guess through a computationally expensive KDF. Overridable for ops rotation.
_FP_SALT = os.environ.get("HATUN_MCP_FP_SALT", "hatun-mcp/api-key-fingerprint/v1").encode()
_FP_ITERATIONS = int(os.environ.get("HATUN_MCP_FP_ITERATIONS", "210000"))
_KEY_PATTERN = re.compile(r"szl_[A-Za-z0-9_-]{1,252}\Z")
_SCOPE_BINDING_PATTERN = re.compile(r"HATUN_MCP_SCOPE_[0-9a-f]{16}\Z")
_VALID_SCOPES = frozenset({"read", "write", "admin"})
_MAX_RPC_BYTES = 256 * 1024
_BODY_TIMEOUT_SECONDS = 10.0

# HTTP is an operator-admitted read-only surface. The complete package catalog
# remains available to trusted local stdio callers; discovery is not permission.
# New/dynamic tools require an explicit review before entering this allowlist.
_HTTP_READ_TOOLS = frozenset({
    "szl_github_estate_snapshot",
    "szl_yuyay_score",
    "szl_formula_evaluate",
})
_HTTP_LOCAL_FORMULAS = frozenset({"puriq", "sigmoid", "liu_hui_pi"})
_HTTP_READ_RESOURCES = frozenset({"hatun://doctrine/locked-numbers"})
_HTTP_METADATA_METHODS = frozenset({
    "initialize", "notifications/initialized", "notifications/cancelled", "ping",
    "tools/list", "resources/list", "resources/templates/list", "prompts/list",
})


def http_auth_configured() -> bool:
    """Observe explicit operator bindings without exposing their fingerprints."""
    return any(
        _SCOPE_BINDING_PATTERN.fullmatch(name) and scope in _VALID_SCOPES
        for name, scope in os.environ.items()
    )


def _http_transport_policy() -> dict:
    return {
        "profile": "operator-read-only",
        "credential_authority": "explicit-operator-scope-binding",
        "portal_validation": "NOT_IMPLEMENTED",
        "tools": sorted(_HTTP_READ_TOOLS),
        "local_formulas": sorted(_HTTP_LOCAL_FORMULAS),
        "resources": sorted(_HTTP_READ_RESOURCES),
        "write_authorization": "UNAVAILABLE",
        "approval_headers": "NOT_TRUSTED",
        "catalog_is_authorization": False,
        "transport": "stateless-streamable-http",
        "legacy_sse": "DISABLED",
    }


def resolve_api_key(raw_key: str | None) -> tuple[str | None, str]:
    """Resolve only a bounded key with an explicit valid operator scope binding.

    A prefix or fingerprint alone is not authentication. This is a local
    operator allowlist, not a customer-portal validation/introspection service.
    The existing PBKDF2 fingerprint and HATUN_MCP_SCOPE_<fingerprint> names are
    retained; absent, empty and unknown scope values fail closed.
    """
    if not isinstance(raw_key, str) or not _KEY_PATTERN.fullmatch(raw_key):
        return None, "read"
    fp = hashlib.pbkdf2_hmac(
        "sha256",
        raw_key.encode(),
        _FP_SALT,
        _FP_ITERATIONS,
    ).hex()[:16]
    scope = os.environ.get(f"HATUN_MCP_SCOPE_{fp}")
    if scope not in _VALID_SCOPES:
        return None, "read"
    return f"client_{fp}", scope


def _transport_error(status: int, code: str) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if status == 401:
        headers["WWW-Authenticate"] = 'Bearer realm="hatun-mcp"'
    return JSONResponse({"error": code}, status_code=status, headers=headers)


def _admit_http_rpc(message) -> JSONResponse | None:
    """Admit a single read-only MCP message before any server dispatch."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _transport_error(400, "invalid_mcp_message")
    method = message.get("method")
    if not isinstance(method, str):
        return _transport_error(400, "invalid_mcp_message")
    if method in _HTTP_METADATA_METHODS:
        return None
    params = message.get("params")
    if not isinstance(params, dict):
        return _transport_error(400, "invalid_mcp_parameters")
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or name not in _HTTP_READ_TOOLS:
            return _transport_error(403, "tool_not_admitted_for_http")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _transport_error(400, "invalid_mcp_parameters")
        if name == "szl_formula_evaluate":
            # Other names, including invalid KL inputs, can fall back to a live
            # backend. This profile admits only guaranteed local formula paths.
            formula = arguments.get("name")
            if not isinstance(formula, str) or formula not in _HTTP_LOCAL_FORMULAS:
                return _transport_error(403, "formula_not_admitted_for_http")
        return None
    if method == "resources/read":
        uri = params.get("uri")
        if isinstance(uri, str) and uri in _HTTP_READ_RESOURCES:
            return None
        return _transport_error(403, "resource_not_admitted_for_http")
    return _transport_error(403, "method_not_admitted_for_http")


# ── SAFE-NOW hardening (R2): real security response headers on every route ──────
# The browser-facing surface is the HTML console at "/"; it ships inline <script>,
# inline <style>, and inline style="" attributes, so script-src/style-src keep
# 'unsafe-inline' (a strict nonce CSP would blank the console). The console fetches
# this server's own routes ONLY (/api/console-state and /pubkey), so connect-src is
# tightened to 'self' — verified against the console source: it makes no off-origin
# fetch, and every number it renders comes from this process's own Python endpoint.
# JSON/MCP responses ignore CSP, so one policy is safe
# for every route. frame-ancestors allows the legitimate HF embed but nothing else;
# we never send X-Frame-Options: DENY (it would break that embed). HSTS is honest
# here — this is a real TLS server.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'self' https://huggingface.co https://*.hf.space"
)
_SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "cross-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for k, v in _SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response


class GovernanceAuthMiddleware:
    """Authenticate and admit every HTTP MCP transport before dispatch.

    ASGI body replay keeps the same bounded, inspected bytes visible to the SDK.
    Legacy SSE is disabled because its long-lived session cannot safely inherit
    an identity from independently authenticated message POST requests.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith(
            ("/mcp", "/sse", "/messages")
        ):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        origin = request.headers.get("origin")
        if origin and ALLOWED_ORIGINS and origin not in ALLOWED_ORIGINS \
                and "*" not in ALLOWED_ORIGINS:
            await _transport_error(403, "origin_not_allowed")(scope, receive, send)
            return
        authorization = request.headers.getlist("authorization")
        api_keys = request.headers.getlist("x-api-key")
        if len(authorization) > 1 or len(api_keys) > 1 or (authorization and api_keys):
            await _transport_error(401, "ambiguous_credentials")(scope, receive, send)
            return
        auth = authorization[0] if authorization else ""
        raw = auth[7:] if auth.lower().startswith("bearer ") else (
            api_keys[0] if api_keys and not authorization else None
        )
        client_id, key_scope = resolve_api_key(raw)
        if client_id is None:
            await _transport_error(401, "operator_key_required")(scope, receive, send)
            return
        if scope["path"].startswith(("/sse", "/messages")):
            await _transport_error(410, "legacy_transport_disabled")(scope, receive, send)
            return

        downstream_receive = receive
        if scope["method"] == "POST":
            content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                await _transport_error(415, "json_content_type_required")(scope, receive, send)
                return
            body = bytearray()
            try:
                async with asyncio.timeout(_BODY_TIMEOUT_SECONDS):
                    while True:
                        event = await receive()
                        if event["type"] == "http.disconnect":
                            return
                        if event["type"] != "http.request":
                            await _transport_error(400, "invalid_mcp_message")(scope, receive, send)
                            return
                        chunk = event.get("body", b"")
                        if len(body) + len(chunk) > _MAX_RPC_BYTES:
                            await _transport_error(413, "mcp_message_too_large")(scope, receive, send)
                            return
                        body.extend(chunk)
                        if not event.get("more_body", False):
                            break
            except TimeoutError:
                await _transport_error(408, "mcp_body_timeout")(scope, receive, send)
                return
            try:
                message = json.loads(body)
            except (ValueError, UnicodeDecodeError, RecursionError):
                await _transport_error(400, "invalid_mcp_message")(scope, receive, send)
                return
            error = _admit_http_rpc(message)
            if error is not None:
                await error(scope, receive, send)
                return
            replayed = False

            async def downstream_receive():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

        tok_client = _ctx_client.set(client_id)
        tok_scope = _ctx_scope.set(key_scope)
        # Unverified request headers are not approval or sovereign authority.
        tok_sov = _ctx_sovereign.set(False)
        tok_sec = _ctx_second_approver.set(None)
        try:
            await self.app(scope, downstream_receive, send)
        finally:
            _ctx_client.reset(tok_client)
            _ctx_scope.reset(tok_scope)
            _ctx_sovereign.reset(tok_sov)
            _ctx_second_approver.reset(tok_sec)


# ── well-known server card (for Smithery / registry scanning) ───────────────────
def _server_card() -> dict:
    tools = []
    # Static, hand-maintained mirror (authoritative for registries behind auth wall):
    card_tools = [
        ("szl_a11oy_code_chat", "Chat with a11oy.code unified open-LLM router"),
        ("szl_killinchu_detect", "Detect/identify a drone from RF/Remote-ID/ADS-B"),
        ("szl_killinchu_cue", "Signed BoE target cue (state-changing, 2-person gate)"),
        ("szl_immune_scan", "a11oy Immune (Hukulla) screen of code/SBOM/image (signed verdict)"),
        ("szl_a11oy_sentinel_scan", "a11oy Sentinel immune scan (twin of szl_immune_scan)"),
        ("szl_companion_reason", "a11oy companion reasoning (grounded; refuses to fabricate)"),
        ("szl_a11oy_operator_reason", "a11oy Operator reasoning (twin of szl_companion_reason)"),
        ("szl_github_estate_snapshot", "Bounded, fixed-target, public-only GitHub estate evidence snapshot"),
        ("szl_khipu_verify", "Verify a Khipu receipt hash + merkle proof"),
        ("szl_lean_verify", "Verify a Lean theorem on lutar-lean kernel"),
        ("szl_puriq_evaluate", "Compute PURIQ P(x,t) + factor breakdown"),
        ("szl_yachay_dome_predict", "Yachay-Dome impact prediction for a track"),
        ("szl_wayra_recent", "Recent WAYRA ingestions (honest stub until WAYRA ships)"),
        ("szl_anatomy_3d_render", "Three.js scene snapshot URL for an organ"),
        ("szl_doctrine_lookup", "Semantic lookup across Doctrine v11/v12/v13 + thesis v20"),
        ("szl_yuyay_score", "13-axis Yuyay breakdown of content"),
        ("szl_thesis_query", "RAG query against thesis-corpus-v18 HF dataset"),
        ("szl_drone_lookup", "Canonical drone DB entry from killinchu"),
        ("szl_formula_evaluate", "Evaluate a doctrine formula primitive (PURIQ P(x,t), KL, sigmoid, Liu Hui pi)"),
        ("szl_lambda_quorum", "Governance-critical Λ verdict under Byzantine n>=3f+1 quorum (n=5,f=1) + BLS aggregate"),
        ("yuyay_gate_check", "Run the 13-axis Yuyay gate over input (input-as-data defense) + Khipu receipt"),
        ("khipu_append_and_verify", "Append a Khipu link and recompute-verify the append-only chain"),
        ("dsse_sign", "Real ECDSA P-256 DSSE envelope (honesty=UNSIGNED when no key in process)"),
        ("mesh_quorum_status", "Byzantine n>=3f+1 mesh-quorum status over named organs"),
        ("puriq_master_tool", "THE named PURIQ entrypoint: Yuyay-13 -> quorum -> Khipu -> DSSE"),
        ("governance_pacbayes_bound", "Published PAC-Bayes (McAllester) generalization bound (F7), real closed-form"),
    ]
    for name, desc in card_tools:
        input_schema = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        } if name == "szl_github_estate_snapshot" else {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
        tools.append({
            "name": name, "description": desc,
            "inputSchema": input_schema,
        })
    return {
        "serverInfo": {"name": "hatun-mcp", "version": "1.0.1",
                       "vendor": "SZL Holdings",
                       "description": "Doctrine-aware MCP server — PURIQ governance "
                                      "(Yuyay-13 gate, Khipu receipts, DSSE-signed "
                                      "responses) extended to the world's agents."},
        "authentication": {"required": True,
                            "schemes": ["apiKey"],
                            "note": "Provide an SZL API key as Authorization: Bearer szl_... "
                                    "An explicit operator scope binding is required."},
        "http_transport_policy": _http_transport_policy(),
        "tools": tools, "resources": [
            {"uri": "hatun://khipu/recent", "description": "Recent Khipu receipts"},
            {"uri": "hatun://doctrine/locked-numbers", "description": "Doctrine v11 LOCKED numbers"},
        ], "prompts": [],
        "governance": {"protocol_revision": DOCTRINE["protocol_revision"],
                       "signer_mode": SIGNER.mode,
                       "doctrine_locked": {k: DOCTRINE[k] for k in
                                           ("lean_declarations", "lean_sorries_total", "yuyay_axes")}},
    }


def _deterministic_json_bytes(value: dict) -> bytes:
    """Serialize public discovery artifacts into one stable UTF-8 byte form."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _exact_source_revision(value: str | None) -> str | None:
    revision = (value or "").strip().lower()
    if len(revision) == 40 and all(
        character in "0123456789abcdef" for character in revision
    ):
        return revision
    return None


def _build_manifest_attestation(
    *,
    manifest_bytes: bytes,
    signer: DsseSigner,
    source_revision: str | None,
) -> dict:
    """Bind the exact served card bytes to an in-toto Statement v1.

    This function has no request input. The caller caches its result once per
    process, so the public GET cannot be repurposed as a signing oracle.
    """
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    revision = _exact_source_revision(source_revision)
    signing_state = "SIGNED" if signer.mode == "ECDSA-P256" else "UNSIGNED"
    statement = {
        "_type": IN_TOTO_STATEMENT_TYPE,
        "subject": [
            {
                "name": MCP_MANIFEST_URI,
                "digest": {"sha256": digest},
            }
        ],
        "predicateType": MCP_MANIFEST_PREDICATE_TYPE,
        "predicate": {
            "manifest": {
                "uri": MCP_MANIFEST_URI,
                "mediaType": "application/json",
                "byteLength": len(manifest_bytes),
            },
            "producer": {
                "service": "hatun-mcp",
                "repository": SOURCE_REPOSITORY,
                "sourceRevision": {
                    "state": "OBSERVED" if revision else "UNAVAILABLE",
                    "value": revision,
                },
            },
            "attestation": {
                "signingState": signing_state,
                "algorithm": "ECDSA-P256" if signing_state == "SIGNED" else None,
                "transparencyLog": "UNAVAILABLE",
            },
            "scope": {
                "integrity": "EXACT_BYTES",
                "runtimeToolParity": "NOT_ATTESTED",
                "mcpServerCardSpecification": "DRAFT_EXTENSION",
            },
        },
    }
    envelope = signer.sign_in_toto(statement)
    signed = envelope is not None
    if signed != (signing_state == "SIGNED"):
        raise RuntimeError("manifest attestation signer state is inconsistent")
    return {
        "schemaVersion": "1.0",
        "manifest": {
            "uri": MCP_MANIFEST_URI,
            "mediaType": "application/json",
            "byteLength": len(manifest_bytes),
            "digest": {"sha256": digest},
        },
        "statement": statement,
        "dsseEnvelope": envelope,
        "signing": {
            "state": signing_state,
            "signerMode": signer.mode,
            "keyid": DSSE_KEY_ID if signed else None,
            "publicKey": f"{PUBLIC_BASE}/pubkey" if signed else None,
            "transparencyLog": "UNAVAILABLE",
        },
        "receiptMinted": False,
    }


# These are immutable process artifacts. Every server-card alias serves the exact
# bytes hashed below, and the fixed attestation is signed at most once per start.
_SERVER_CARD_BYTES = _deterministic_json_bytes(_server_card())
# Bind the published card's tool names (read back out of the exact served bytes)
# so /api/console-state can MEASURE parity between the static discovery card and
# the live runtime registry instead of assuming they agree.
set_card_tool_names(
    [tool["name"] for tool in json.loads(_SERVER_CARD_BYTES)["tools"]]
)
_MANIFEST_ATTESTATION = _build_manifest_attestation(
    manifest_bytes=_SERVER_CARD_BYTES,
    signer=SIGNER,
    source_revision=os.environ.get("SZL_GIT_SHA"),
)
_MANIFEST_ATTESTATION_BYTES = _deterministic_json_bytes(_MANIFEST_ATTESTATION)


async def server_card(request: Request):
    return Response(
        _SERVER_CARD_BYTES,
        media_type="application/json",
        headers=_DISCOVERY_HEADERS,
    )


# Convenience aliases for the draft server-card discovery extension. This
# project's canonical document lives at /.well-known/mcp/server-card.json; the
# short, guessable paths are the ones a human pokes at first. They serve the SAME
# real card (not a redirect to avoid the http-scheme downgrade some proxies apply
# to 3xx Location headers) so "inspect the server card" resolves no matter which
# path the caller tried.
async def server_card_alias(request: Request):
    return Response(
        _SERVER_CARD_BYTES,
        media_type="application/json",
        headers=_DISCOVERY_HEADERS,
    )


async def manifest_attestation(request: Request):
    """Return the fixed in-toto/DSSE binding for the public MCP card."""
    return Response(
        _MANIFEST_ATTESTATION_BYTES,
        media_type="application/json",
        headers=_DISCOVERY_HEADERS,
    )


# The agent-connect descriptor: the real, working way to wire an MCP client into
# this server. Points at the trailing-slash /mcp/ endpoint (the streamable-HTTP
# app is mounted there; the bare /mcp 307-redirects, and behind the HF reverse
# proxy that redirect's Location downgrades to http://, which trips strict
# clients). Giving clients /mcp/ directly avoids the redirect entirely.
def _connect_info() -> dict:
    base = PUBLIC_BASE
    return {
        "service": "hatun-mcp",
        "transport": "streamable-http",
        "mcp_endpoint": f"{base}/mcp/",
        "sse_endpoint": None,
        "authentication": {
            "scheme": "apiKey",
            "header": "Authorization: Bearer szl_...",
            "note": "An explicitly admitted operator key is required; a key prefix alone is not authentication.",
        },
        "http_transport_policy": _http_transport_policy(),
        "server_card": f"{base}/.well-known/mcp/server-card.json",
        "manifest_attestation": MCP_MANIFEST_ATTESTATION_URI,
        "clients": {
            "claude_desktop": {
                "mcpServers": {
                    "hatun-mcp": {
                        "command": "npx",
                        "args": ["-y", "mcp-remote", f"{base}/mcp/",
                                 "--header", "Authorization: Bearer szl_YOUR_KEY"],
                    }
                }
            },
            "cursor": {
                "mcpServers": {
                    "hatun-mcp": {
                        "url": f"{base}/mcp/",
                        "headers": {"Authorization": "Bearer szl_YOUR_KEY"},
                    }
                }
            },
        },
        "docs": "https://github.com/szl-holdings/hatun-mcp",
    }


async def connect(request: Request):
    return JSONResponse(_connect_info())


async def build_info(request: Request):
    """Expose the exact protected Git revision injected by the Space deployer."""
    revision = os.environ.get("SZL_GIT_SHA", "").strip().lower()
    observed = len(revision) == 40 and all(
        character in "0123456789abcdef" for character in revision
    )
    return JSONResponse(
        {
            "service": "hatun-mcp",
            "build": {
                "state": "OBSERVED" if observed else "UNAVAILABLE",
                "revision": revision if observed else None,
            },
            "runtime": {
                "transport": "streamable-http",
                "protocol_revision": DOCTRINE["protocol_revision"],
            },
            "receipt_minted": False,
        },
        status_code=200 if observed else 503,
        headers={"Cache-Control": "no-store"},
    )


async def console_state_route(request: Request):
    """Real, in-request state for the human console.

    Reads the live FastMCP tool registry, the live Khipu chain, the signer and
    the injected build revision. Values that cannot be read are returned with an
    honest label instead of a number — nothing here is seeded or carried over.
    """
    payload = console_state(
        mcp=mcp,
        khipu=KHIPU,
        signer=SIGNER,
        doctrine=DOCTRINE,
        organ_summary=getattr(_server, "ORGAN_CATALOG_SUMMARY", None),
        public_base=PUBLIC_BASE,
    )
    auth_ready = http_auth_configured()
    payload["health"]["authentication"] = "CONFIGURED" if auth_ready else "UNAVAILABLE"
    if not auth_ready:
        payload["health"]["readiness"] = "NOT-READY"
    payload["http_transport_policy"] = _http_transport_policy()
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


async def healthz(request: Request):
    return JSONResponse({"status": "ok", "service": "hatun-mcp",
                         "chain_verified": KHIPU.verify(),
                         "signer_mode": SIGNER.mode,
                         "protocol_revision": DOCTRINE["protocol_revision"]})


async def readyz(request: Request):
    """Report release readiness without hiding an unsigned or broken chain.

    Liveness and release readiness are deliberately separate. The process can
    remain alive while the receipt chain is invalid or the real signing key is
    absent; callers must not infer signed-tool readiness from ``/healthz``.
    """
    try:
        chain_verified = KHIPU.verify() is True
        chain_state = "VERIFIED" if chain_verified else "FAILED"
    except Exception:
        chain_verified, chain_state = False, "UNAVAILABLE"
    signer_mode = observed_signer_mode(SIGNER)
    signer_ready = signer_mode == "ECDSA-P256"
    auth_ready = http_auth_configured()
    ready = chain_verified and signer_ready and auth_ready
    return JSONResponse(
        {
            "status": "ready" if ready else "not_ready",
            "service": "hatun-mcp",
            "ready": ready,
            "checks": {
                "receipt_chain": chain_state,
                "signer": "CONFIGURED" if signer_ready else "UNAVAILABLE",
                "authentication": "CONFIGURED" if auth_ready else "UNAVAILABLE",
            },
            "signer_mode": signer_mode,
            "protocol_revision": DOCTRINE["protocol_revision"],
        },
        status_code=200 if ready else 503,
        headers={"Cache-Control": "no-store"},
    )


async def pubkey(request: Request):
    pem = SIGNER.public_key_pem()
    if pem is None:
        return PlainTextResponse("PLACEHOLDER: no signing key in this process.", status_code=200)
    return PlainTextResponse(pem, media_type="application/x-pem-file")


# The canonical JSON service descriptor.
# Returned to API/MCP clients (Accept: application/json, or no text/html). MCP
# transport handshakes never see HTML.
_INDEX_JSON = {
    "service": "hatun-mcp", "tagline": "the great context protocol",
    "mcp_endpoint": "/mcp/", "sse_endpoint": None,
    "server_card": "/.well-known/mcp/server-card.json",
    "manifest_attestation": MCP_MANIFEST_ATTESTATION_PATH,
    "connect": "/connect",
    "healthz": "/healthz", "readyz": "/readyz", "build_info": "/api/build-info",
    "console_state": "/api/console-state", "pubkey": "/pubkey",
    "docs": "https://github.com/szl-holdings/hatun-mcp",
}


def _prefers_html(request: Request) -> bool:
    """Content-negotiate the root: serve the human console ONLY to browsers.

    A browser sends ``Accept: text/html...`` and ranks it above (or without)
    ``application/json``. MCP/SSE clients send ``application/json`` (or ``*/*``
    with no explicit html preference) and must keep receiving the JSON
    descriptor. We honor an explicit JSON request even if html is also listed:
    if the caller names application/json at all, we return JSON (safest for
    machine clients); html is served only when html is requested and json is
    NOT explicitly named.
    """
    accept = request.headers.get("accept", "").lower()
    if "application/json" in accept:
        return False
    return "text/html" in accept


async def index(request: Request):
    if _prefers_html(request):
        # no-store so the agentic live fetches always reflect current state.
        return HTMLResponse(CONSOLE_HTML, headers={"Cache-Control": "no-store"})
    return JSONResponse(_INDEX_JSON)


# Compose the Starlette app with the stateless Streamable HTTP transport.
#
# IMPORTANT: FastMCP's Streamable HTTP app runs a session manager that MUST be started
# via the ASGI lifespan. When we mount it under a parent Starlette app, the parent must
# adopt the child app's lifespan, otherwise the session manager never starts and /mcp
# returns 404. We build the streamable app at its own root path "" so the parent Mount
# at "/mcp" maps cleanly (no trailing-slash redirect), and we pass its lifespan up.
import contextlib

http_app = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(app):
    # Run the child app's session manager and task group.
    async with contextlib.AsyncExitStack() as stack:
        if http_app.router.lifespan_context is not None:
            await stack.enter_async_context(http_app.router.lifespan_context(http_app))
        yield


app = Starlette(
    routes=[
        Route("/", index),
        Route("/healthz", healthz),
        Route("/api/build-info", build_info),
        Route("/api/console-state", console_state_route),
        Route("/readyz", readyz),
        Route("/pubkey", pubkey),
        Route("/connect", connect),
        Route("/.well-known/mcp/server-card.json", server_card),
        Route("/.well-known/mcp", server_card_alias),
        Route("/.well-known/mcp/", server_card_alias),
        Route(MCP_MANIFEST_ATTESTATION_PATH, manifest_attestation),
        Route("/server-card", server_card_alias),
        Route("/card", server_card_alias),
        Mount("/mcp", app=http_app),
    ],
    lifespan=lifespan,
)
app.add_middleware(GovernanceAuthMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
