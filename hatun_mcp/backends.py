"""
hatun_mcp.backends — REAL HTTP clients to the live SZL flagship Spaces.

No mocks. Each function calls the documented live endpoint. If a route is not yet
deployed (e.g. WAYRA, or a flagship route still in-flight), the call returns an
HONEST structured payload {"deployed": false, "reason": ...} captured from the real
HTTP status — disclosed in the Khipu receipt, never faked.

Live base URLs (verified from the SZL Space inventory, 2026-06-01):
  a11oy       https://szlholdings-a11oy.hf.space
  amaru       https://szlholdings-amaru.hf.space
  sentra      https://szlholdings-sentra.hf.space
  killinchu   https://szlholdings-killinchu.hf.space
  rosie       https://szlholdings-rosie.hf.space
  lean-kernel https://szlholdings-lean-kernel.hf.space
  anatomy-3d  https://szlholdings-anatomy-3d.hf.space

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx

BASES = {
    "a11oy": os.environ.get("SZL_A11OY_URL", "https://szlholdings-a11oy.hf.space"),
    "amaru": os.environ.get("SZL_AMARU_URL", "https://szlholdings-amaru.hf.space"),
    "sentra": os.environ.get("SZL_SENTRA_URL", "https://szlholdings-sentra.hf.space"),
    "killinchu": os.environ.get("SZL_KILLINCHU_URL", "https://szlholdings-killinchu.hf.space"),
    "rosie": os.environ.get("SZL_ROSIE_URL", "https://szlholdings-rosie.hf.space"),
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


async def sentra_inspect(target: dict) -> BackendResult:
    return await _post("sentra", ["/api/sentra/v1/inspect", "/v1/threats"], target)


async def rosie_ask(question: str, context: Any) -> BackendResult:
    return await _post("rosie", ["/v1/brain/jack", "/v1/brain/ask", "/api/rosie/v1/rag"],
                       {"question": question, "context": context})


async def rosie_rag(question: str) -> BackendResult:
    return await _post("rosie", ["/api/rosie/v1/rag", "/v1/rag"],
                       {"query": question, "corpus": "thesis-corpus-v18"})


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
