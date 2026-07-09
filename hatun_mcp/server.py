"""
hatun_mcp.server — HATUN-MCP, the doctrine-aware MCP server.

"the great context protocol" (Quechua: hatun = great + MCP). A new bridging element
in the PURIQ Kallpa wires that extends SZL governance — Yuyay-13 gate, HUKLLA
tripwires, Khipu receipts, the PURIQ master formula — to the world's MCP clients.

Transports: Streamable HTTP (/mcp) + legacy SSE (/sse) for hosted use; stdio for
local. Every tool invocation:
  1. authenticates the client (API key -> client_id); anonymous => declined.
  2. runs the Yuyay-13 gate on its input (input-as-data; OWASP MCP06 defense).
  3. computes Hatun_MCP(client_id) reputation factor in [0,1].
  4. requires a 2-person Yuyay gate if the tool is state-changing.
  5. calls the REAL flagship backend within a latency budget.
  6. emits a Khipu receipt on success AND failure.
  7. returns a DSSE-signed response with the receipt hash attached.

SPDX-License-Identifier: Apache-2.0
Author: Yachay (CTO authority) · Built by Perplexity Computer Agent · 2026-06-01
"""
from __future__ import annotations

import json
import os
import time
from contextvars import ContextVar
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import backends as B
from .governance import (
    DOCTRINE,
    ClientRegistry,
    DsseSigner,
    KhipuChain,
    YUYAY_AXES,
    YUYAY_FLOORS,
    hatun_mcp_factor,
    hukla_check,
    puriq_utility,
    yuyay_gate,
)

# ── Global governance singletons ────────────────────────────────────────────────
KHIPU = KhipuChain()
SIGNER = DsseSigner()
CLIENTS = ClientRegistry()

# Per-request context (populated by the auth/transport layer; see server_http.py).
_ctx_client: ContextVar[Optional[str]] = ContextVar("client_id", default=None)
_ctx_scope: ContextVar[str] = ContextVar("scope", default="read")
_ctx_sovereign: ContextVar[bool] = ContextVar("sovereign", default=False)
_ctx_second_approver: ContextVar[Optional[str]] = ContextVar("second_approver", default=None)

DEFAULT_LATENCY_BUDGET = float(os.environ.get("HATUN_MCP_LATENCY_BUDGET", "5.0"))
ALLOW_ANON = os.environ.get("HATUN_MCP_ALLOW_ANON", "false").lower() == "true"

# DNS-rebinding / Host-header validation. Behind the HF Spaces reverse proxy the
# forwarded Host is the public hostname, which the SDK's default (localhost-only)
# policy rejects with HTTP 421 "Invalid Host header". We explicitly allow the
# hosted hostname (and operator-supplied extras via env) while keeping our own
# Origin validation in GovernanceAuthMiddleware as the primary DNS-rebinding
# defense. Set HATUN_MCP_ALLOWED_HOSTS="*" to disable host pinning entirely.
_hosts_env = os.environ.get(
    "HATUN_MCP_ALLOWED_HOSTS",
    "szlholdings-hatun-mcp.hf.space,*.hf.space,localhost,127.0.0.1",
)
_allowed_hosts = [h.strip() for h in _hosts_env.split(",") if h.strip()]
_origins_env = os.environ.get(
    "HATUN_MCP_ALLOWED_ORIGINS",
    "https://szlholdings-hatun-mcp.hf.space,https://smithery.ai,http://localhost",
)
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
_disable_host_pin = ("*" in _allowed_hosts) or ("*" in _allowed_origins)
_transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=not _disable_host_pin,
    allowed_hosts=_allowed_hosts if not _disable_host_pin else ["*"],
    allowed_origins=_allowed_origins if not _disable_host_pin else ["*"],
)

mcp = FastMCP(
    "hatun-mcp",
    transport_security=_transport_security,
    # Serve the MCP endpoints at the mount root so a Starlette Mount("/mcp") maps to
    # the actual MCP endpoint with no double-prefix and no trailing-slash 404.
    streamable_http_path="/",
    sse_path="/",
    message_path="/messages/",
    # Stateless Streamable HTTP: each POST is self-contained (no server-held session
    # id). Required behind the HF Spaces reverse proxy, which does not guarantee
    # worker affinity — a stateful session manager would 400 on the follow-up call.
    stateless_http=True,
    json_response=True,
    instructions=(
        "HATUN-MCP — the doctrine-aware MCP server for SZL Holdings. Every tool call "
        "is governed by the PURIQ formula: a Yuyay-13 gate runs on the input, a Khipu "
        "receipt is emitted on success and failure, and the response is DSSE-signed. "
        "An API key is required; anonymous calls are declined. State-changing tools "
        "(e.g. szl_killinchu_cue) require a 2-person Yuyay approval."
    ),
)


# ── The governed-invocation wrapper ─────────────────────────────────────────────
def _set_test_context(client_id="szl_test_demo", scope="admin",
                      sovereign=False, second_approver=None):
    """Used by tests / stdio local mode to set a default authenticated context."""
    _ctx_client.set(client_id)
    _ctx_scope.set(scope)
    _ctx_sovereign.set(sovereign)
    _ctx_second_approver.set(second_approver)


def _scope_ok(scope: str, needs: str) -> bool:
    order = {"read": 0, "write": 1, "admin": 2}
    return order.get(scope, 0) >= order.get(needs, 0)


async def governed(
    *,
    tool: str,
    operation_id: str,
    gate_text: str,
    needs_scope: str = "read",
    state_changing: bool = False,
    latency_budget: Optional[float] = None,
    narrative_axes: bool = False,
    backend_coro=None,
):
    """Run one tool through the full PURIQ pipeline. Returns the response dict that
    the tool hands back to the MCP client (always JSON-serializable)."""
    t0 = time.time()
    budget = latency_budget or DEFAULT_LATENCY_BUDGET
    client_id = _ctx_client.get()
    scope = _ctx_scope.get()
    sovereign = _ctx_sovereign.get()
    second = _ctx_second_approver.get()

    authenticated = bool(client_id) or ALLOW_ANON
    scope_ok = _scope_ok(scope, needs_scope)
    two_person = bool(second) and second != client_id

    # 1. Yuyay-13 gate on input (input-as-data).
    yuyay = yuyay_gate(gate_text)

    # 2. reputation + Hatun factor.
    reputation = CLIENTS.reputation(client_id)
    factor = hatun_mcp_factor(
        authenticated=authenticated, scope_ok=scope_ok, reputation=reputation,
        state_changing=state_changing, two_person=two_person,
    )

    # 3. Hard declines (default-decline; receipted) BEFORE any backend call.
    decline = None
    if not authenticated:
        decline = {"reason": "no_api_key", "owasp_class": "MCP07",
                   "message": "Anonymous tool calls are declined. Provide an SZL API key."}
    elif not scope_ok:
        decline = {"reason": "insufficient_scope", "owasp_class": "MCP02",
                   "message": f"Tool needs scope '{needs_scope}', key has '{scope}'."}
    elif state_changing and not two_person:
        decline = {"reason": "two_person_gate_required", "owasp_class": "MCP02",
                   "message": ("State-changing tool requires a 2-person Yuyay gate. "
                               "Provide a distinct second approver "
                               "(X-Second-Approver header).")}
    elif not yuyay.passed:
        decline = {"reason": "yuyay_axis_below_floor", "owasp_class": "MCP06",
                   "message": (f"Input failed Yuyay-13 axis '{yuyay.blocked_axis}' "
                               f"(value {yuyay.scores.get(yuyay.blocked_axis):.2f} "
                               f"< floor {YUYAY_FLOORS.get(yuyay.blocked_axis):.2f}). "
                               "Tool input treated as data, not instructions.")}

    if decline is not None:
        # Close the un-awaited backend coroutine to avoid a leak (we decline before calling it).
        if backend_coro is not None and hasattr(backend_coro, "close"):
            backend_coro.close()
        tripwire = "T09" if decline["reason"] == "yuyay_axis_below_floor" else None
        score = puriq_utility(lam=1.0, yuyay=yuyay, hukla_tripwire=tripwire,
                              khipu_chain_ok=True, hatun_factor=factor)
        r = KHIPU.emit(
            tool=tool, client_id=client_id or "anonymous", operation_id=operation_id,
            status="declined", tripwire=tripwire,
            yuyay_min_axis=yuyay.min_axis_value, hatun_mcp_factor=factor,
            puriq_score=score, detail={"decline": decline}, signer=SIGNER,
        )
        if client_id:
            CLIENTS.record(client_id, clean=False)
        return _wrap(
            status="declined", data=None, gate_transparency={**decline, "yuyay": yuyay.scores},
            receipt=r, narrative_axes=narrative_axes, tool=tool, sovereign=sovereign,
        )

    # 4. Backend call (REAL) within latency budget.
    backend = None
    err = None
    try:
        if backend_coro is not None:
            backend = await backend_coro
    except Exception as e:  # defensive; backends already swallow transport errors
        err = f"{type(e).__name__}: {e}"

    latency = time.time() - t0
    chain_ok = KHIPU.verify()
    tripwire = hukla_check(
        chain_ok=chain_ok, yuyay=yuyay, latency_s=latency,
        latency_budget_s=budget, action_space=1,
    )

    status = "success"
    if err is not None:
        status = "failure"
    elif backend is not None and isinstance(backend, dict) and backend.get("error"):
        status = "failure" if not backend.get("deployed", True) else "success"
        # a non-deployed backend is an honest 'not-live' success-with-disclosure, not a crash

    score = puriq_utility(lam=1.0, yuyay=yuyay, hukla_tripwire=tripwire,
                          khipu_chain_ok=chain_ok, hatun_factor=factor)

    detail = {
        "latency_s": round(latency, 4),
        "latency_budget_s": budget,
        "backend_error": err,
        "backend": _summ(backend),
        "sovereign_mode": sovereign,
    }
    r = KHIPU.emit(
        tool=tool, client_id=client_id, operation_id=operation_id,
        status=status, tripwire=tripwire, yuyay_min_axis=yuyay.min_axis_value,
        hatun_mcp_factor=factor, puriq_score=score, detail=detail, signer=SIGNER,
    )
    CLIENTS.record(client_id, clean=(tripwire is None and status == "success"))

    return _wrap(
        status=status, data=backend, gate_transparency=None, receipt=r,
        narrative_axes=narrative_axes, tool=tool, sovereign=sovereign,
    )


def _summ(backend: Any) -> Any:
    if backend is None:
        return None
    if isinstance(backend, dict):
        return {k: backend.get(k) for k in ("deployed", "http_status", "endpoint", "error", "reason")}
    return str(backend)[:500]


def _wrap(*, status, data, gate_transparency, receipt, narrative_axes, tool, sovereign):
    out = {
        "tool": tool,
        "status": status,
        "data": data.get("data") if isinstance(data, dict) and "data" in data else data,
        "backend": _summ(data),
        "khipu_receipt": {
            "receipt_id": receipt.receipt_id,
            "continuum_hash": receipt.continuum_hash,
            "prev_hash": receipt.prev_hash,
            "chain_verified": receipt.chain_verified,
            "tripwire": receipt.tripwire,
            "puriq_score": receipt.puriq_score,
            "hatun_mcp_factor": receipt.hatun_mcp_factor,
        },
        "dsse": receipt.dsse,
        "governance": {
            "protocol_revision": DOCTRINE["protocol_revision"],
            "sovereign_mode": sovereign,
            "signer_mode": SIGNER.mode,
        },
    }
    if gate_transparency is not None:
        out["gate_transparency"] = gate_transparency
    if narrative_axes:
        out["narrative"] = _narrative_wrap(tool, status, data)
    return out


def _narrative_wrap(tool, status, data):
    """Frontier #6: Hatun-Willay 5-axis narrative wrap (Origin/Mechanism/Evidence/Stakes/Invitation)."""
    return {
        "origin": f"Hatun-MCP ('the great context protocol') exposed tool {tool} as a "
                  f"PURIQ-governed Kallpa wire.",
        "mechanism": "Yuyay-13 gate on input, Hatun_MCP reputation factor, Khipu receipt "
                     "on success and failure, DSSE-signed response.",
        "evidence": f"Khipu receipt is verifiable; chain recompute='verify our logs'. "
                    f"Doctrine v11 LOCKED: {DOCTRINE['lean_declarations']} decl / "
                    f"{DOCTRINE['lean_sorries_total']} sorries / {DOCTRINE['yuyay_axes']} axes.",
        "stakes": "Extends SZL governance to every MCP client (Claude Desktop, Cursor, "
                  "Continue, Zed, Goose) — Warhacker 16–19 Jun 2026, Defense Unicorns, Series-A.",
        "invitation": "Verify the receipt: call szl_khipu_verify with the continuum_hash.",
    }


# ════════════════════════════════════════════════════════════════════════════════
#  THE 15 TOOLS
# ════════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def szl_a11oy_code_chat(messages: list, model: Optional[str] = None,
                              narrative_axes: bool = False) -> dict:
    """Chat with a11oy.code — the unified open-LLM router (7-tier, GREEN-first).
    Calls a11oy POST /v1/router. messages = OpenAI-style [{role, content}, ...]."""
    txt = " ".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
    return await governed(
        tool="szl_a11oy_code_chat", operation_id="a11oy.router", gate_text=txt,
        needs_scope="read", narrative_axes=narrative_axes,
        backend_coro=B.a11oy_router(messages, model, sovereign=_ctx_sovereign.get()),
    )


@mcp.tool()
async def szl_killinchu_detect(rf_signature: Optional[dict] = None,
                               remote_id_data: Optional[dict] = None,
                               adsb: Optional[dict] = None) -> dict:
    """Detect/identify a drone or track from RF signature, Remote-ID, or ADS-B.
    Calls killinchu POST /counter-uas/identify."""
    sig = {"rf_signature": rf_signature, "remote_id_data": remote_id_data, "adsb": adsb}
    return await governed(
        tool="szl_killinchu_detect", operation_id="killinchu.identify",
        gate_text=json.dumps(sig)[:5000], needs_scope="read",
        backend_coro=B.killinchu_identify(sig),
    )


@mcp.tool()
async def szl_killinchu_cue(track: dict, asset_value_polygon: dict) -> dict:
    """Generate a signed Ballistic-of-Effect (BoE) target cue package. STATE-CHANGING:
    requires a 2-person Yuyay gate (provide X-Second-Approver). Calls killinchu POST /v1/cue."""
    return await governed(
        tool="szl_killinchu_cue", operation_id="killinchu.cue",
        gate_text=json.dumps({"track": track})[:5000], needs_scope="write",
        state_changing=True,
        backend_coro=B.killinchu_cue(track, asset_value_polygon),
    )


@mcp.tool()
async def szl_immune_scan(code: Optional[str] = None, sbom: Optional[dict] = None,
                          image: Optional[str] = None) -> dict:
    """a11oy Immune (Hukulla) inline screen — screen code, an SBOM, or a container
    image for threat signatures. Calls the live a11oy immune organ
    POST /api/a11oy/v1/immune/verdict (the screen IS the signed verdict route).

    (Renamed 2026-06-16 from the retired codename tool; see DEPRECATED.md.)"""
    target = {"code": code, "sbom": sbom, "image": image}
    return await governed(
        tool="szl_immune_scan", operation_id="immune.screen",
        gate_text=(code or json.dumps(target))[:8000], needs_scope="read",
        backend_coro=B.immune_screen(target),
    )


@mcp.tool()
async def szl_companion_reason(question: str, context: Any = None) -> dict:
    """Ask the a11oy companion to reason over a question + context. Calls the live
    a11oy companion organ POST /api/a11oy/v1/companion/ask (answers only from live
    platform data; refuses to fabricate).

    (Renamed 2026-06-16 from the retired codename tool; see DEPRECATED.md.)"""
    return await governed(
        tool="szl_companion_reason", operation_id="companion.ask",
        gate_text=str(question)[:8000], needs_scope="read",
        backend_coro=B.companion_ask(question, context),
    )


# ── a11oy-named honest twins (kept for consumers already on these names) ──────────
# The purged sentra/rosie/amaru backends are now served by the live honest a11oy
# organs (immune / companion / llm). These a11oy-named tools route to the SAME
# live a11oy organ backend as the renamed tools above — honest names, no codename.
@mcp.tool()
async def szl_a11oy_sentinel_scan(code: Optional[str] = None, sbom: Optional[dict] = None,
                                  image: Optional[str] = None) -> dict:
    """a11oy Sentinel inline immune screen — a11oy-named twin of szl_immune_scan.
    Screen code, an SBOM, or a container image for threat signatures. Calls the
    live a11oy immune organ POST /api/a11oy/v1/immune/verdict."""
    target = {"code": code, "sbom": sbom, "image": image}
    return await governed(
        tool="szl_a11oy_sentinel_scan", operation_id="immune.screen",
        gate_text=(code or json.dumps(target))[:8000], needs_scope="read",
        backend_coro=B.immune_screen(target),
    )


@mcp.tool()
async def szl_a11oy_operator_reason(question: str, context: Any = None) -> dict:
    """a11oy Operator reasoning — a11oy-named twin of szl_companion_reason. Reason
    over a question + context. Calls the live a11oy companion organ
    POST /api/a11oy/v1/companion/ask."""
    return await governed(
        tool="szl_a11oy_operator_reason", operation_id="companion.ask",
        gate_text=str(question)[:8000], needs_scope="read",
        backend_coro=B.companion_ask(question, context),
    )

@mcp.tool()
async def szl_khipu_verify(receipt_hash: str, merkle_proof: Optional[list] = None,
                           flagship: str = "a11oy") -> dict:
    """Verify a Khipu receipt hash (+ optional merkle proof) on a flagship.
    Calls <flagship> POST /khipu/verify."""
    return await governed(
        tool="szl_khipu_verify", operation_id="khipu.verify",
        gate_text=str(receipt_hash), needs_scope="read",
        backend_coro=B.khipu_verify(flagship, receipt_hash, merkle_proof),
    )


@mcp.tool()
async def szl_lean_verify(theorem_name: str) -> dict:
    """Verify a Lean theorem against the live lutar-lean kernel.
    Calls lean-kernel POST /lean-verify."""
    return await governed(
        tool="szl_lean_verify", operation_id="lean.verify",
        gate_text=str(theorem_name), needs_scope="read",
        backend_coro=B.lean_verify(theorem_name),
    )


@mcp.tool()
async def szl_puriq_evaluate(action: dict, context: dict) -> dict:
    """Compute the PURIQ master operator P(x,t) for an action + return the factor
    breakdown (Λ, Yuyay-13, HUKLLA, Khipu, Hatun_MCP). Also queries a11oy policy."""
    yz = yuyay_gate(json.dumps(action) + json.dumps(context))
    client_id = _ctx_client.get()
    factor = hatun_mcp_factor(
        authenticated=bool(client_id) or ALLOW_ANON, scope_ok=True,
        reputation=CLIENTS.reputation(client_id), state_changing=False, two_person=False)
    score = puriq_utility(lam=1.0, yuyay=yz, hukla_tripwire=(None if yz.passed else "T09"),
                          khipu_chain_ok=KHIPU.verify(), hatun_factor=factor)
    breakdown = {
        "lambda": 1.0,
        "yuyay_13": {"passed": yz.passed, "min_axis": yz.min_axis_name,
                     "min_value": yz.min_axis_value, "scores": yz.scores},
        "hukla_tripwire": None if yz.passed else "T09",
        "khipu_chain_ok": KHIPU.verify(),
        "hatun_mcp_factor": factor,
        "P_x_t": score,
    }
    return await governed(
        tool="szl_puriq_evaluate", operation_id="puriq.evaluate",
        gate_text=json.dumps(action)[:5000], needs_scope="read",
        backend_coro=B.a11oy_policy_evaluate(action, {**context, "_puriq_local": breakdown}),
    )


@mcp.tool()
async def szl_yachay_dome_predict(track_id: str, horizon_seconds: int = 30) -> dict:
    """Yachay-Dome impact prediction for a track over a horizon.
    Calls killinchu POST /v1/predict-impact."""
    return await governed(
        tool="szl_yachay_dome_predict", operation_id="killinchu.predict_impact",
        gate_text=str(track_id), needs_scope="read",
        backend_coro=B.killinchu_predict_impact(track_id, horizon_seconds),
    )


@mcp.tool()
async def szl_wayra_recent(source: Optional[str] = None, top_k: int = 10) -> dict:
    """Recent WAYRA ingestions. WAYRA agent is not yet deployed — returns an honest
    'not yet deployed' payload (disclosed in the receipt, never faked)."""
    async def _stub():
        return B.BackendResult(
            deployed=False, http_status=None, endpoint="(WAYRA not yet deployed)",
            error="route_not_live",
            reason="WAYRA agent has not shipped yet. Honest stub per Doctrine HR-4 "
                   "(Zero-Bandaid). When WAYRA ships, this calls its /recent endpoint.",
            data=None,
        )
    return await governed(
        tool="szl_wayra_recent", operation_id="wayra.recent",
        gate_text=str(source or ""), needs_scope="read", backend_coro=_stub(),
    )


@mcp.tool()
async def szl_anatomy_3d_render(organ: str, animation_state: str = "idle") -> dict:
    """Return a URL to a Three.js scene snapshot of an organ in the SZL 3D anatomy."""
    async def _scene():
        return B.BackendResult(
            deployed=True, http_status=200,
            endpoint=B.anatomy_scene_url(organ, animation_state),
            error=None, data={"scene_url": B.anatomy_scene_url(organ, animation_state),
                              "organ": organ, "animation_state": animation_state})
    return await governed(
        tool="szl_anatomy_3d_render", operation_id="anatomy.render",
        gate_text=f"{organ} {animation_state}", needs_scope="read", backend_coro=_scene(),
    )


@mcp.tool()
async def szl_doctrine_lookup(query: str) -> dict:
    """Semantic lookup across SZL Doctrine v11/v12/v13 + thesis v20.
    Routed via the a11oy companion grounded-RAG over the doctrine corpus."""
    return await governed(
        tool="szl_doctrine_lookup", operation_id="doctrine.lookup",
        gate_text=str(query)[:5000], needs_scope="read",
        backend_coro=B.companion_rag("DOCTRINE: " + query),
    )


@mcp.tool()
async def szl_yuyay_score(content: str) -> dict:
    """Return the 13-axis Yuyay breakdown of any content (the heart's scoring)."""
    async def _local():
        yz = yuyay_gate(content)
        return B.BackendResult(deployed=True, http_status=200, endpoint="(local Yuyay-13)",
                               error=None, data={"passed": yz.passed, "scores": yz.scores,
                                                 "floors": YUYAY_FLOORS, "axes": YUYAY_AXES,
                                                 "blocked_axis": yz.blocked_axis})
    return await governed(
        tool="szl_yuyay_score", operation_id="yuyay.score",
        gate_text=str(content)[:8000], needs_scope="read", backend_coro=_local(),
    )


@mcp.tool()
async def szl_thesis_query(question: str) -> dict:
    """RAG query against the thesis-corpus-v18 HF dataset. Calls the a11oy
    companion grounded-RAG."""
    return await governed(
        tool="szl_thesis_query", operation_id="thesis.query",
        gate_text=str(question)[:5000], needs_scope="read",
        backend_coro=B.companion_rag(question),
    )


@mcp.tool()
async def szl_drone_lookup(model_or_signature: str) -> dict:
    """Return the canonical drone DB entry from the killinchu drone database.
    Calls killinchu GET /v1/drones."""
    return await governed(
        tool="szl_drone_lookup", operation_id="killinchu.drones",
        gate_text=str(model_or_signature), needs_scope="read",
        backend_coro=B.killinchu_drones(model_or_signature),
    )


@mcp.tool()
async def szl_formula_evaluate(name: str, args: Optional[dict] = None) -> dict:
    """Evaluate a named doctrine formula primitive (real closed-form arithmetic).
    Known: 'puriq' (master operator P(x,t)), 'kl_divergence', 'sigmoid', 'liu_hui_pi'.
    Unknown names are forwarded to the live lutar-lean kernel /formula-eval route."""
    return await governed(
        tool="szl_formula_evaluate", operation_id="formula.evaluate",
        gate_text=f"{name} {json.dumps(args or {})}"[:5000], needs_scope="read",
        backend_coro=B.formula_evaluate(name, args or {}),
    )


# ── Resources: live Khipu chain + server card ───────────────────────────────────
@mcp.resource("hatun://khipu/recent")
def khipu_recent() -> str:
    """Recent Khipu receipts emitted by this server (audit trail)."""
    return json.dumps({"chain_verified": KHIPU.verify(), "recent": KHIPU.recent(20)}, indent=2)


@mcp.resource("hatun://doctrine/locked-numbers")
def locked_numbers() -> str:
    """Doctrine v11 LOCKED canonical numbers (from counter, HR-6)."""
    return json.dumps(DOCTRINE, indent=2)


# ── PURIQ governance tools (WU-5): register the five gates as first-class MCP tools.
# Reuses the SAME live KHIPU chain / SIGNER / CLIENTS singletons (no parallel state),
# so puriq_master shares the audit trail with the 15 backend tools above.
from .tools import register_governance_tools  # noqa: E402

register_governance_tools(mcp, KHIPU, SIGNER, CLIENTS)


# ════════════════════════════════════════════════════════════════════════════════
#  GOVERNANCE-CRITICAL: Byzantine quorum + BLS aggregate over N organs
# ════════════════════════════════════════════════════════════════════════════════
from .dsse import BlsAggregator
from .loop import run_bounded_loop
from .quorum import QuorumConfig, OrganVote, decide as quorum_decide

BLS = BlsAggregator()
QUORUM_CFG = QuorumConfig(n=5, f=1)


@mcp.tool()
async def szl_lambda_quorum(action: dict, context: Any = None,
                            organs: Optional[list] = None) -> dict:
    """Governance-critical Λ verdict under a Byzantine n>=3f+1 quorum (n=5, f=1).

    Fans the action out to the five SZL organs' policy/verdict routes, collects each
    organ's verdict, and decides only if >= 2f+1 (=3) reachable organs AGREE and
    >= 3f+1 (=4) organs are reachable. Each organ's contribution mints a Khipu
    receipt; the participating receipts are BLS-aggregated into one signature. The
    full quorum tally + aggregate ride in `governance.quorum`. HONEST: each organ's
    reachability is captured from the real HTTP status; any organ whose policy route
    is not live contributes an honest miss and the degradation is disclosed.

    OUROBOROS LOOP (in-code, receipt-closed). The organ fan-out — the repo's actual
    multi-step orchestration path — runs inside `hatun_mcp.loop.run_bounded_loop`: a
    HARD step budget (env `HATUN_MCP_LOOP_MAX_STEPS`, safe default 12), per-step
    trace entries, and an HONEST exit reason (`converged` | `budget_exhausted` |
    `error`, never fake convergence). The trace rides in `governance.loop` and in the
    top-level Khipu receipt detail. Default behavior is unchanged: the default
    5-organ set is well under the budget, so it always exits `converged`. Doctrine:
    "bounded, terminating, receipt-closed" (Λ = Conjecture 1, never a theorem).
    """
    from .adapters import build_adapters
    client_id = _ctx_client.get()
    sovereign = _ctx_sovereign.get()
    targets = organs or ["a11oy", "immune", "companion", "llm", "killinchu"]
    ads = build_adapters()
    gate_text = json.dumps(action)[:5000]

    votes: list = []
    organ_receipts: list = []

    async def _organ_step(idx: int, organ: str, trace) -> Optional[OrganVote]:
        """One bounded loop iteration: query one organ, mint its receipt, tally."""
        ad = ads.get(organ)
        if ad is None:
            trace.add("action", f"organ '{organ}': no adapter registered; skipped")
            return None
        # Each organ evaluates the action via its policy/verdict route.
        trace.add("network", f"organ '{organ}': policy_evaluate")
        res = await ad.call("policy_evaluate", {"action": action, "context": context or {}})
        reachable = bool(res.get("deployed")) and res.get("error") in (None, "")
        verdict = None
        if reachable and isinstance(res.get("data"), dict):
            d = res["data"]
            verdict = d.get("verdict") or d.get("decision") or d.get("allow")
        # Mint a per-organ Khipu receipt for this contribution (success or honest miss).
        rr = KHIPU.emit(
            tool="szl_lambda_quorum", client_id=client_id or "anonymous",
            operation_id=f"{organ}.lambda_verdict",
            status="success" if reachable else "failure",
            tripwire=None, yuyay_min_axis=None, hatun_mcp_factor=0.0,
            puriq_score=0.0,
            detail={"organ": organ, "reachable": reachable,
                    "verdict": verdict, "backend": _summ(res)},
            signer=SIGNER,
        )
        organ_receipts.append((organ, rr.continuum_hash))
        vote = OrganVote(organ=organ, reachable=reachable, verdict=verdict,
                         receipt_hash=rr.continuum_hash,
                         detail={"backend": _summ(res)})
        votes.append(vote)
        return vote

    # Bounded Ouroboros walk over the organ fan-out (no unbounded loop on this path).
    _, loop_trace = await run_bounded_loop(list(targets), _organ_step)
    loop = loop_trace.to_dict()

    qresult = quorum_decide(votes, QUORUM_CFG)
    agg = BLS.aggregate(organ_receipts)

    # Wrap through governed() for the uniform envelope (Yuyay gate + top-level receipt).
    async def _payload():
        return B.BackendResult(
            deployed=True, http_status=200, endpoint="(hatun-mcp quorum)", error=None,
            data={"quorum": qresult.to_dict(), "bls_aggregate": agg.to_dict(),
                  "loop": loop},
        )
    out = await governed(
        tool="szl_lambda_quorum", operation_id="lambda.quorum", gate_text=gate_text,
        needs_scope="read", backend_coro=_payload(),
    )
    out["governance"]["quorum"] = qresult.to_dict()
    out["governance"]["bls_aggregate"] = agg.to_dict()
    out["governance"]["loop"] = loop
    out["governance"]["sovereign_mode"] = sovereign
    return out


# ── Dynamic organ-tool registration (live catalogs) ─────────────────────────────
# At import time, fetch each organ's live MCP catalog and register <organ>_<tool>
# tools through governed(). Honest: unreachable organs register zero tools + a
# single <organ>_status introspection tool. Disabled in unit tests via env to keep
# the test suite hermetic (no network).
ORGAN_CATALOG_SUMMARY: dict = {}


def register_dynamic_organ_tools() -> dict:
    """Fetch live organ catalogs and register their tools. Returns the summary."""
    from .adapters import build_adapters, register_organ_tools
    return register_organ_tools(mcp, build_adapters(), governed)


if os.environ.get("HATUN_MCP_DISABLE_DYNAMIC", "false").lower() != "true":
    try:
        ORGAN_CATALOG_SUMMARY = register_dynamic_organ_tools()
    except Exception as _e:  # never let organ probing break server import
        ORGAN_CATALOG_SUMMARY = {"_error": f"{type(_e).__name__}: {_e}"}


if __name__ == "__main__":
    # Local stdio mode (for Claude Desktop / Cursor local). Sets a demo authenticated
    # context so local users aren't anonymous-declined; hosted mode uses real API keys.
    if os.environ.get("HATUN_MCP_LOCAL_AUTH", "true").lower() == "true":
        _set_test_context()
    mcp.run()
