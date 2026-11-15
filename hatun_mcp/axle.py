"""hatun_mcp.axle — bounded SECONDARY-oracle client for Axiom's AXLE Lean engine.

AXLE (https://axle.axiommath.ai, arXiv 2606.26442) is AxiomMath's cloud Lean 4
verification API: verify_proof, check, sorry2lemma, extract_proof_states,
disprove, merge, normalize and friends. This module consolidates that surface
behind SZL doctrine with explicit tweaks — this is a BRIDGE, not a mirror:

  * SECONDARY ORACLE ONLY. The estate's local Lean kernel (szl_lean_verify /
    lean-kernel) stays the PRIMARY, authorizing oracle. An AXLE result may
    corroborate; it can never authorize a merge, a publish, or a promotion.
    Every result carries the envelope {oracle: "axle", role:
    "secondary_corroborating", authorizing: false, local_kernel_primary: true}.
  * FAIL-CLOSED ABSTAIN. No AXLE_API_KEY configured, unreachable service,
    transport error, non-200 response, or oversized payload => an honest
    ABSTAIN result (deployed=false / error classified), never a pass. AXLE
    never turns silence into success.
  * FIXED TARGET. One base URL (env HATUN_MCP_AXLE_URL), one allowlisted
    endpoint set, POST api/v1/<method> / GET v1/<resource>. No redirects,
    no inherited proxy (trust_env=False), no arbitrary URL is ever accepted.
  * BOUNDED I/O. Request payloads are capped (AXLE_MAX_CONTENT_BYTES); responses
    are capped (AXLE_MAX_RESPONSE_BYTES); per-call timeout_seconds is clamped to
    [1, AXLE_MAX_TIMEOUT_SECONDS] (upstream max 900 s).
  * KEY HYGIENE. The bearer key is read from AXLE_API_KEY (or
    HATUN_MCP_AXLE_API_KEY) and placed ONLY in the Authorization header. It is
    never logged, echoed, hashed into receipts, or included in any result.
    Provider exception text and response bodies are never forwarded as error
    messages; errors are classified to short stable codes.

Honest boundary disclosures:
  * Verification of UNTRUSTED Lean via any metaprogramming-rich service
    (AXLE's own docs) is not adversarially sound; this bridge inherits that
    boundary. Corroboration here strengthens evidence; it does not replace the
    local kernel, and it does not constitute human review.
  * AXLE is a third-party service: Lean source sent through this bridge leaves
    the estate boundary. Operators enable the key knowingly.

SPDX-License-Identifier: Apache-2.0
Author: SZL Holdings — AXLE bridge (instill decision 2026-11-15, doctrine v11)
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

# httpx is imported lazily inside the transport so this module stays importable
# (and its pure allowlist/envelope logic unit-testable) without network deps.

AXLE_BASE = os.environ.get("HATUN_MCP_AXLE_URL", "https://axle.axiommath.ai").rstrip("/")

# The fixed allowlist: every AXLE tool endpoint (docs index 2026-11-15, v1.9.0).
AXLE_ENDPOINTS = frozenset({
    "verify_proof", "check", "extract_theorems", "extract_decls",
    "extract_proof_states", "rename", "theorem2lemma", "theorem2sorry",
    "merge", "simplify_theorems", "repair_proofs", "have2lemma",
    "have2sorry", "sorry2lemma", "disprove", "normalize",
})

AXLE_MAX_CONTENT_BYTES = 262_144          # 256 KiB request cap per call
AXLE_MAX_RESPONSE_BYTES = 4_194_304        # 4 MiB response read cap
AXLE_MAX_TIMEOUT_SECONDS = 900.0           # upstream documented maximum
AXLE_DEFAULT_TIMEOUT_SECONDS = 120.0
AXLE_STATUS_TIMEOUT_SECONDS = 15.0
AXLE_RESULT_KEYS = ("deployed", "http_status", "endpoint", "error", "reason", "data")

# Standard Lean axioms accepted in every kernel-checked proof (Weil/Stacks
# hygiene benchmark). Surfaced for the caller's own statement-fidelity review.
AXLE_STANDARD_AXIOMS = frozenset({
    "propext", "Classical.choice", "Quot.sound",
})


class AxleResult(dict):
    """BackendResult-compatible honest envelope (deployed/http_status/...)."""

    @property
    def ok(self) -> bool:
        return bool(self.get("deployed", True)) and self.get("error") is None


def _axle_key() -> Optional[str]:
    """Read the AXLE bearer key. Never logged, never returned in any result."""
    key = os.environ.get("HATUN_MCP_AXLE_API_KEY") or os.environ.get("AXLE_API_KEY")
    return key.strip() if isinstance(key, str) and key.strip() else None


def _abstain(error: str, reason: str, endpoint: str) -> AxleResult:
    """Honest fail-closed ABSTAIN: disclosed, never a pass, never faked."""
    return AxleResult(
        deployed=False, http_status=None, endpoint=endpoint, error=error,
        reason=reason,
        data=_envelope("abstain", None, error),
    )


def _envelope(reading: str, axle_response: Any, error: Optional[str]) -> dict:
    """The SZL tweak: every AXLE result is framed as a SECONDARY oracle."""
    return {
        "oracle": "axle",
        "role": "secondary_corroborating",
        "authorizing": False,
        "local_kernel_primary": True,
        "estate_reading": reading,          # corroborated | not_corroborated | abstain
        "axle": axle_response,
        "axle_error": error,
        "note": ("AXLE corroborates only; the estate's local Lean kernel "
                 "remains the authorizing oracle. Not human review."),
    }


def _clamp_timeout(timeout_seconds: Any) -> float:
    try:
        t = float(timeout_seconds)
    except (TypeError, ValueError):
        t = AXLE_DEFAULT_TIMEOUT_SECONDS
    return max(1.0, min(t, AXLE_MAX_TIMEOUT_SECONDS))


def _payload_bytes(method: str, payload: dict) -> Optional[bytes]:
    body = dict(payload or {})
    body["timeout_seconds"] = _clamp_timeout(body.get("timeout_seconds"))
    try:
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        return None
    if len(data) > AXLE_MAX_CONTENT_BYTES:
        return None
    return data


def _classify_error(body: dict) -> Optional[str]:
    """Short stable code for AXLE's in-band error fields (never raw text)."""
    if "internal_error" in body:
        return "axle_internal_error"
    if "user_error" in body:
        return "axle_user_error"
    et = body.get("error_type")
    if et == "LeanResourceExceeded":
        return "axle_lean_resource_exceeded"
    if et == "LeanTimeout":
        return "axle_lean_timeout"
    if "error" in body:
        return "axle_error"
    return None


def _reading(method: str, body: dict) -> str:
    """Conservative estate reading of an in-band AXLE response."""
    if _classify_error(body) is not None:
        return "not_corroborated"
    okay = body.get("okay")
    if okay is False:
        return "not_corroborated"
    if body.get("failed_declarations"):
        return "not_corroborated"
    if method == "verify_proof" and body.get("negation") and \
            body["negation"].get("okay") is True and body.get("okay") is False:
        return "not_corroborated"
    return "corroborated" if okay is True else "reading_needs_caller_review"


def _budget(timeout_seconds: Any) -> float:
    """Latency budget for governed(): axle timeout plus a bounded margin."""
    return _clamp_timeout(timeout_seconds) + 30.0


def axle_not_configured(method: str = "status") -> AxleResult:
    """Honest not-configured disclosure (fail-closed, no key => no call)."""
    return _abstain(
        "axle_not_configured",
        "AXLE_API_KEY (or HATUN_MCP_AXLE_API_KEY) is not configured for this "
        "process, so no AXLE call was attempted. Honest ABSTAIN — disclosed, "
        "not faked. The estate's local kernel remains the authorizing oracle.",
        f"{AXLE_BASE}/api/v1/{method}",
    )


async def axle_run(method: str, payload: Optional[dict] = None) -> AxleResult:
    """Run ONE allowlisted AXLE endpoint. Fail-closed; never raises to the tool."""
    if method not in AXLE_ENDPOINTS:
        return _abstain(
            "axle_endpoint_not_allowlisted",
            f"Endpoint '{method}' is not in the fixed AXLE allowlist; no "
            "request was made. Fail-closed.",
            f"{AXLE_BASE}/api/v1/{method}",
        )
    key = _axle_key()
    if key is None:
        return axle_not_configured(method)
    data = _payload_bytes(method, payload or {})
    if data is None:
        return _abstain(
            "axle_payload_rejected",
            "Payload is not JSON-serializable or exceeds the request byte cap "
            f"({AXLE_MAX_CONTENT_BYTES}); no request was made. Fail-closed.",
            f"{AXLE_BASE}/api/v1/{method}",
        )
    url = f"{AXLE_BASE}/api/v1/{method}"
    timeout_s = _clamp_timeout((payload or {}).get("timeout_seconds"))

    import httpx  # lazy: keep pure logic importable without network deps

    headers = {
        "Authorization": f"Bearer {key}",
        "X-Request-Source": "szl-hatun-mcp-bridge",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(
            timeout=timeout_s + 30.0, follow_redirects=False, trust_env=False,
        ) as client:
            r = await client.post(url, content=data, headers=headers)
    except Exception as exc:  # sanitized: exception text never forwarded
        return _abstain(
            "axle_transport_failure",
            f"AXLE transport did not complete ({type(exc).__name__}); no "
            "verdict is available. Honest ABSTAIN — disclosed, not faked.",
            url,
        )
    if r.status_code != 200:
        # Classified HTTP outcome; body text is not forwarded.
        return AxleResult(
            deployed=False, http_status=r.status_code, endpoint=url,
            error=f"axle_http_{r.status_code}",
            reason=("AXLE answered with a non-200 status; body withheld "
                    "(third-party content is not forwarded)."),
            data=_envelope("abstain", None, f"axle_http_{r.status_code}"),
        )
    if len(r.content) > AXLE_MAX_RESPONSE_BYTES:
        return _abstain("axle_response_oversized",
                        "AXLE response exceeded the response byte cap and was "
                        "discarded. Honest ABSTAIN — disclosed, not faked.", url)
    try:
        body = json.loads(r.text)
    except ValueError:
        return _abstain("axle_response_not_json",
                        "AXLE response was not valid JSON; discarded. Honest "
                        "ABSTAIN — disclosed, not faked.", url)
    err = _classify_error(body)
    reading = _reading(method, body) if err is None else "not_corroborated"
    return AxleResult(
        deployed=True, http_status=200, endpoint=url, error=err,
        reason=None if err is None else
        "AXLE returned an in-band error (classified; raw text withheld).",
        data=_envelope(reading, body, err),
    )


async def axle_get(resource: str, timeout_seconds: float = AXLE_STATUS_TIMEOUT_SECONDS
                   ) -> AxleResult:
    """GET one fixed AXLE resource ('status' | 'environments'). Fail-closed."""
    if resource not in ("status", "environments"):
        return _abstain(
            "axle_resource_not_allowlisted",
            f"Resource '{resource}' is not one of the fixed GET resources; no "
            "request was made. Fail-closed.",
            f"{AXLE_BASE}/v1/{resource}",
        )
    key = _axle_key()
    if key is None:
        return axle_not_configured(resource)
    url = f"{AXLE_BASE}/v1/{resource}"
    import httpx  # lazy: keep pure logic importable without network deps
    headers = {"Authorization": f"Bearer {key}",
               "X-Request-Source": "szl-hatun-mcp-bridge"}
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, follow_redirects=False, trust_env=False,
        ) as client:
            r = await client.get(url, headers=headers)
    except Exception as exc:  # sanitized: exception text never forwarded
        return _abstain(
            "axle_transport_failure",
            f"AXLE transport did not complete ({type(exc).__name__}); honest "
            "ABSTAIN — disclosed, not faked.",
            url,
        )
    if r.status_code != 200:
        return AxleResult(
            deployed=False, http_status=r.status_code, endpoint=url,
            error=f"axle_http_{r.status_code}",
            reason=("AXLE answered with a non-200 status; body withheld "
                    "(third-party content is not forwarded)."),
            data=_envelope("abstain", None, f"axle_http_{r.status_code}"),
        )
    try:
        body = json.loads(r.text)
    except ValueError:
        return _abstain("axle_response_not_json",
                        "AXLE response was not valid JSON; discarded. Honest "
                        "ABSTAIN — disclosed, not faked.", url)
    return AxleResult(
        deployed=True, http_status=200, endpoint=url, error=None, reason=None,
        data=_envelope("corroborated", body, None),
    )
