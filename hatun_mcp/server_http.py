"""
hatun_mcp.server_http — hosted HTTP entrypoint (Streamable HTTP /mcp + legacy /sse).

Wraps the FastMCP app in a Starlette application that:
  * authenticates each request via the SZL API key (Authorization: Bearer szl_... ,
    or X-Api-Key). Resolves key -> client_id + scope and sets the request contextvars.
  * validates the Origin header (DNS-rebinding defense; MCP transport requirement).
  * honors X-Sovereign-Mode and X-Second-Approver headers (Frontier #4, 2-person gate).
  * serves /.well-known/mcp/server-card.json so registries (Smithery) can enumerate
    the 15 tools even behind the auth wall.
  * serves /healthz and /pubkey (DSSE verification key).

Run:  uvicorn hatun_mcp.server_http:app --host 0.0.0.0 --port 7860
SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import hashlib
import json
import os

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from .server import (
    SIGNER, CLIENTS, KHIPU, mcp,
    _ctx_client, _ctx_scope, _ctx_sovereign, _ctx_second_approver,
)
from .governance import DOCTRINE

ALLOWED_ORIGINS = set(
    o.strip() for o in os.environ.get(
        "HATUN_MCP_ALLOWED_ORIGINS",
        "https://szlholdings-hatun-mcp.hf.space,https://smithery.ai,http://localhost",
    ).split(",")
)


def resolve_api_key(raw_key: str | None) -> tuple[str | None, str]:
    """Resolve an SZL API key to (client_id, scope).

    The authoritative store is the customer-portal (customer_surface/API_KEY_SYSTEM.md);
    this gateway derives a deterministic client_id from sha256(key) and reads scope from
    the key's env binding. A key shaped 'szl_{env}_{flagship?}_{rand}' is accepted; the
    client_id is the key fingerprint so the same caller keeps a stable reputation.
    """
    if not raw_key:
        return None, "read"
    if not raw_key.startswith("szl_"):
        return None, "read"
    fp = hashlib.sha256(raw_key.encode()).hexdigest()[:16]
    # scope: an explicit override env var maps fingerprints -> scope; default read.
    # admin/write keys are provisioned by the portal; demo keys are read.
    scope = os.environ.get(f"HATUN_MCP_SCOPE_{fp}", "read")
    return f"client_{fp}", scope


class GovernanceAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Origin validation (DNS-rebinding defense) — only enforce for /mcp & /sse.
        if request.url.path.startswith(("/mcp", "/sse", "/messages")):
            origin = request.headers.get("origin")
            if origin and ALLOWED_ORIGINS and origin not in ALLOWED_ORIGINS \
                    and "*" not in ALLOWED_ORIGINS:
                return JSONResponse(
                    {"error": "origin_not_allowed", "owasp_class": "transport-origin"},
                    status_code=403,
                )
        # API-key auth.
        auth = request.headers.get("authorization", "")
        raw = auth[7:] if auth.lower().startswith("bearer ") else request.headers.get("x-api-key")
        client_id, scope = resolve_api_key(raw)
        tok_client = _ctx_client.set(client_id)
        tok_scope = _ctx_scope.set(scope)
        tok_sov = _ctx_sovereign.set(request.headers.get("x-sovereign-mode", "").lower() == "true")
        tok_sec = _ctx_second_approver.set(request.headers.get("x-second-approver"))
        try:
            response = await call_next(request)
        finally:
            _ctx_client.reset(tok_client)
            _ctx_scope.reset(tok_scope)
            _ctx_sovereign.reset(tok_sov)
            _ctx_second_approver.reset(tok_sec)
        return response


# ── well-known server card (for Smithery / registry scanning) ───────────────────
def _server_card() -> dict:
    tools = []
    # FastMCP exposes the registered tools; build a static card from their schemas.
    try:
        import anyio
        listed = anyio.from_thread.run(mcp.list_tools) if False else None  # noqa
    except Exception:
        listed = None
    # Static, hand-maintained mirror (authoritative for registries behind auth wall):
    card_tools = [
        ("szl_a11oy_code_chat", "Chat with a11oy.code unified open-LLM router"),
        ("szl_killinchu_detect", "Detect/identify a drone from RF/Remote-ID/ADS-B"),
        ("szl_killinchu_cue", "Signed BoE target cue (state-changing, 2-person gate)"),
        ("szl_sentra_scan", "Sentra immune scan of code/SBOM/image"),
        ("szl_a11oy_sentinel_scan", "a11oy Sentinel immune scan (alias of szl_sentra_scan)"),
        ("szl_rosie_reason", "Rosie brain-jack reasoning"),
        ("szl_a11oy_operator_reason", "a11oy Operator reasoning (alias of szl_rosie_reason)"),
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
    ]
    for name, desc in card_tools:
        tools.append({
            "name": name, "description": desc,
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
        })
    return {
        "serverInfo": {"name": "hatun-mcp", "version": "1.0.0",
                       "vendor": "SZL Holdings",
                       "description": "Doctrine-aware MCP server — PURIQ governance "
                                      "(Yuyay-13 gate, Khipu receipts, DSSE-signed "
                                      "responses) extended to the world's agents."},
        "authentication": {"required": not (os.environ.get("HATUN_MCP_ALLOW_ANON", "false").lower() == "true"),
                            "schemes": ["apiKey", "oauth2"],
                            "note": "Provide an SZL API key as Authorization: Bearer szl_... "
                                    "Anonymous calls are declined and receipted."},
        "tools": tools, "resources": [
            {"uri": "hatun://khipu/recent", "description": "Recent Khipu receipts"},
            {"uri": "hatun://doctrine/locked-numbers", "description": "Doctrine v11 LOCKED numbers"},
        ], "prompts": [],
        "governance": {"protocol_revision": DOCTRINE["protocol_revision"],
                       "signer_mode": SIGNER.mode,
                       "doctrine_locked": {k: DOCTRINE[k] for k in
                                           ("lean_declarations", "lean_sorries_total", "yuyay_axes")}},
    }


async def server_card(request: Request):
    return JSONResponse(_server_card())


async def healthz(request: Request):
    return JSONResponse({"status": "ok", "service": "hatun-mcp",
                         "chain_verified": KHIPU.verify(),
                         "signer_mode": SIGNER.mode,
                         "protocol_revision": DOCTRINE["protocol_revision"]})


async def pubkey(request: Request):
    pem = SIGNER.public_key_pem()
    if pem is None:
        return PlainTextResponse("PLACEHOLDER: no signing key in this process.", status_code=200)
    return PlainTextResponse(pem, media_type="application/x-pem-file")


async def index(request: Request):
    return JSONResponse({
        "service": "hatun-mcp", "tagline": "the great context protocol",
        "mcp_endpoint": "/mcp", "sse_endpoint": "/sse",
        "server_card": "/.well-known/mcp/server-card.json",
        "healthz": "/healthz", "pubkey": "/pubkey",
        "docs": "https://github.com/szl-holdings/hatun-mcp",
    })


# Compose the Starlette app: mount FastMCP's SSE + Streamable HTTP apps.
#
# IMPORTANT: FastMCP's Streamable HTTP app runs a session manager that MUST be started
# via the ASGI lifespan. When we mount it under a parent Starlette app, the parent must
# adopt the child app's lifespan, otherwise the session manager never starts and /mcp
# returns 404. We build the streamable app at its own root path "" so the parent Mount
# at "/mcp" maps cleanly (no trailing-slash redirect), and we pass its lifespan up.
import contextlib

http_app = mcp.streamable_http_app()
sse_app = mcp.sse_app()


@contextlib.asynccontextmanager
async def lifespan(app):
    # Run both child apps' lifespans (session managers, task groups).
    async with contextlib.AsyncExitStack() as stack:
        if http_app.router.lifespan_context is not None:
            await stack.enter_async_context(http_app.router.lifespan_context(http_app))
        if sse_app.router.lifespan_context is not None:
            await stack.enter_async_context(sse_app.router.lifespan_context(sse_app))
        yield


app = Starlette(
    routes=[
        Route("/", index),
        Route("/healthz", healthz),
        Route("/pubkey", pubkey),
        Route("/.well-known/mcp/server-card.json", server_card),
        Mount("/mcp", app=http_app),
        Mount("/sse", app=sse_app),
        Mount("/messages", app=sse_app),
    ],
    lifespan=lifespan,
)
app.add_middleware(GovernanceAuthMiddleware)
