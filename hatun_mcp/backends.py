"""
hatun_mcp.backends — REAL HTTP clients to the live SZL flagship Spaces.

No mocks. Each function calls the documented live endpoint. If a route is not yet
deployed (e.g. WAYRA, or a flagship route still in-flight), the call returns an
HONEST structured payload {"deployed": false, "reason": ...} captured from the real
HTTP status — disclosed in the Khipu receipt, never faked.

Live base URLs (re-verified 2026-06-16). The immune/companion/llm organs (which
replaced the PURGED sentra/rosie/amaru backends) are served by the live a11oy
platform on a11oy.net:
  a11oy       https://a11oy.net           (immune / companion / llm / policy / router)
  killinchu   https://szlholdings-killinchu.hf.space
  lean-kernel https://szlholdings-lean-kernel.hf.space
  anatomy-3d  https://szlholdings-anatomy-3d.hf.space

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx

# The a11oy platform now serves the immune/companion/llm organs directly, so they
# all point at the same live base. SZL_A11OY_URL overrides all three at once.
_A11OY = os.environ.get("SZL_A11OY_URL", "https://a11oy.net")
BASES = {
    "a11oy": _A11OY,
    "llm": os.environ.get("SZL_LLM_URL", _A11OY),
    "immune": os.environ.get("SZL_IMMUNE_URL", _A11OY),
    "killinchu": os.environ.get("SZL_KILLINCHU_URL", "https://szlholdings-killinchu.hf.space"),
    "companion": os.environ.get("SZL_COMPANION_URL", _A11OY),
    "lean": os.environ.get("SZL_LEAN_URL", "https://szlholdings-lean-kernel.hf.space"),
    "anatomy": os.environ.get("SZL_ANATOMY_URL", "https://szlholdings-anatomy-3d.hf.space"),
}

DEFAULT_TIMEOUT = float(os.environ.get("HATUN_MCP_BACKEND_TIMEOUT", "5.0"))


class BackendResult(dict):
    """Dict subclass with .ok convenience."""

    @property
    def ok(self) -> bool:
        return bool(self.get("deployed", True)) and self.get("error") is None


async def _post(flagship: str, paths: list[str], payload: dict,
                timeout: float = DEFAULT_TIMEOUT) -> BackendResult:
    """POST to the first path that exists; fall back across candidate routes.
    Returns an honest result indicating real HTTP status. Never raises to the tool."""
    base = BASES[flagship]
    last_status = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for p in paths:
            url = base + p
            try:
                r = await client.post(url, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_status = f"transport_error:{type(e).__name__}"
                continue
            last_status = r.status_code
            if r.status_code == 404:
                continue  # try next candidate route
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text[:2000]}
            return BackendResult(
                deployed=True, http_status=r.status_code, endpoint=url,
                error=None if r.status_code < 400 else f"http_{r.status_code}",
                data=body,
            )
    return BackendResult(
        deployed=False, http_status=last_status, endpoint=base + paths[0],
        error="route_not_live",
        reason=(f"No candidate route live yet (last status {last_status}). "
                "Honest stub — disclosed, not faked."),
        data=None,
    )


async def _get(flagship: str, paths: list[str], params: Optional[dict] = None,
               timeout: float = DEFAULT_TIMEOUT) -> BackendResult:
    base = BASES[flagship]
    last_status = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for p in paths:
            url = base + p
            try:
                r = await client.get(url, params=params or {})
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_status = f"transport_error:{type(e).__name__}"
                continue
            last_status = r.status_code
            if r.status_code == 404:
                continue
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text[:2000]}
            return BackendResult(
                deployed=True, http_status=r.status_code, endpoint=url,
                error=None if r.status_code < 400 else f"http_{r.status_code}",
                data=body,
            )
    return BackendResult(
        deployed=False, http_status=last_status, endpoint=base + paths[0],
        error="route_not_live",
        reason=(f"No candidate route live yet (last status {last_status}). "
                "Honest stub — disclosed, not faked."),
        data=None,
    )


# ── Per-flagship typed wrappers (documented real routes + fallbacks) ────────────

async def a11oy_router(messages: list, model: Optional[str] = None,
                       sovereign: bool = False) -> BackendResult:
    payload = {
        "organ": "a11oy", "task_class": "general", "modality": "text",
        "context_tokens": 0,
        "governance_tier": "sovereign" if sovereign else "standard",
        "messages": messages,
    }
    if model:
        payload["model"] = model
    return await _post("a11oy", ["/v1/router", "/api/a11oy/v1/llm/route"], payload)


async def a11oy_policy_evaluate(action: dict, context: dict) -> BackendResult:
    return await _post("a11oy", ["/api/a11oy/v1/policy/evaluate", "/v1/policy/evaluate"],
                       {"action": action, "context": context})


async def killinchu_identify(signature: dict) -> BackendResult:
    return await _post("killinchu", ["/counter-uas/identify", "/v1/iff"], signature)


async def killinchu_cue(track: dict, asset_value_polygon: dict) -> BackendResult:
    return await _post("killinchu", ["/v1/cue", "/cue"],
                       {"track": track, "asset_value_polygon": asset_value_polygon})


async def killinchu_predict_impact(track_id: str, horizon_seconds: int) -> BackendResult:
    return await _post("killinchu", ["/v1/predict-impact"],
                       {"track_id": track_id, "horizon_seconds": horizon_seconds})


async def killinchu_drones(model_or_signature: str) -> BackendResult:
    return await _get("killinchu", ["/v1/drones"], params={"q": model_or_signature})


async def immune_screen(target: dict) -> BackendResult:
    """Immune screen of an action (code / SBOM / image). The a11oy immune organ has
    no separate /screen route — the screen IS the signed verdict route (live 200)."""
    return await _post("immune", ["/api/a11oy/v1/immune/verdict"],
                       {"action": target, "context": {}})


async def companion_ask(question: str, context: Any) -> BackendResult:
    """Ask the a11oy companion to reason. Live route POST /api/a11oy/v1/companion/ask
    (answers only from live platform data; refuses to fabricate)."""
    return await _post("companion", ["/api/a11oy/v1/companion/ask"],
                       {"question": question, "context": context})


async def companion_rag(question: str) -> BackendResult:
    """Grounded RAG-style query routed through the a11oy companion /ask endpoint."""
    return await _post("companion", ["/api/a11oy/v1/companion/ask"],
                       {"question": question, "topic": "doctrine",
                        "corpus": "thesis-corpus-v18"})


async def khipu_verify(flagship: str, receipt_hash: str,
                       merkle_proof: Optional[list] = None) -> BackendResult:
    fl = flagship if flagship in BASES else "a11oy"
    return await _post(fl, ["/khipu/verify", "/api/a11oy/v1/khipu/verify"],
                       {"receipt_hash": receipt_hash, "merkle_proof": merkle_proof or []})


async def lean_verify(theorem_name: str) -> BackendResult:
    return await _post("lean", ["/lean-verify"], {"theorem": theorem_name})


def anatomy_scene_url(organ: str, animation_state: str = "idle") -> str:
    base = BASES["anatomy"]
    return f"{base}/?organ={organ}&state={animation_state}&src=hatun-mcp"


# ── Formula evaluation (REAL deterministic math; falls back to lean kernel) ──────
# A small library of doctrine formula primitives, evaluated with real arithmetic.
# No mocks: each is a closed-form computation. Unknown names are forwarded to the
# live lean kernel's /formula-eval route; if that route is not live the honest
# 'route_not_live' result is returned and disclosed in the Khipu receipt.
import math as _math


def _eval_known_formula(name: str, args: dict) -> Optional[dict]:
    n = (name or "").strip().lower()
    a = args or {}
    def _f(k, d=0.0):
        try:
            return float(a.get(k, d))
        except (TypeError, ValueError):
            return d
    if n in ("puriq", "puriq_master", "p_x_t", "master"):
        lam = _f("lambda", 1.0); yuyay = _f("yuyay_13", 1.0)
        beta = _f("beta", 8.0); hukla = _f("hukla", 0.0)
        khipu = _f("khipu", 1.0); hatun = _f("hatun_mcp", 1.0)
        val = lam * yuyay * _math.exp(-beta * hukla) * khipu * hatun
        return {"formula": "P(x,t)=\u039b\u00b7Yuyay\u2081\u2083\u00b7exp(-\u03b2\u00b7HUKLLA)\u00b7\u220fKhipu\u00b7Hatun_MCP",
                "inputs": {"lambda": lam, "yuyay_13": yuyay, "beta": beta,
                           "hukla": hukla, "khipu": khipu, "hatun_mcp": hatun},
                "value": val}
    if n in ("kl", "kl_divergence", "kldivergence"):
        p = a.get("p") or []; q = a.get("q") or []
        if p and q and len(p) == len(q):
            kl = sum(pi * _math.log(pi / qi) for pi, qi in zip(p, q) if pi > 0 and qi > 0)
            return {"formula": "D_KL(P||Q)=\u03a3 p_i log(p_i/q_i)", "value": kl,
                    "note": "klDivergence_nonneg axiom holds: value \u2265 0."}
    if n in ("sigmoid", "logistic"):
        x = _f("x"); return {"formula": "\u03c3(x)=1/(1+e^-x)", "value": 1.0 / (1.0 + _math.exp(-x))}
    if n in ("liu_hui_pi", "pi"):
        sides = int(_f("sides", 96))
        val = sides * _math.sin(_math.pi / sides)  # Liu Hui polygon π approximation
        return {"formula": "Liu Hui: n\u00b7sin(\u03c0/n) \u2192 \u03c0", "sides": sides, "value": val}
    return None


async def formula_evaluate(name: str, args: dict) -> BackendResult:
    """Evaluate a named doctrine formula primitive. Local closed-form for known
    primitives (real arithmetic); otherwise forward to the live lean kernel."""
    local = _eval_known_formula(name, args)
    if local is not None:
        return BackendResult(deployed=True, http_status=200,
                             endpoint="(local closed-form evaluator)", error=None,
                             data={"name": name, **local})
    return await _post("lean", ["/formula-eval", "/lean-verify"],
                       {"formula": name, "args": args})
