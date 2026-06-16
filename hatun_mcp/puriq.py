"""hatun_mcp.puriq — the PURIQ orchestrator: the single operational entrypoint.

Composes the REAL governance primitives from hatun_mcp.governance into one named
operator:

    PURIQ(input, context) -> (Lambda in [0,1], DSSE-signed Khipu receipt, traceparent)

Pipeline (honest, no mocks):
    1. Yuyay-13 gate on the input            (governance.yuyay_gate)
    2. Mesh quorum over the named organs     (Byzantine n >= 3f+1)
    3. HUKLLA tripwire check                 (governance.hukla_check)
    4. Khipu append (one link)               (governance.KhipuChain.emit)
    5. DSSE-sign the receipt                 (governance.DsseSigner)
    6. Compose the master-formula scalar     (governance.puriq_utility)

The aggregator Lambda is Conjecture 1 (NEVER a theorem). Here it is consumed as an
input scalar in [0,1]; the composition gates ARE real.

SPDX-License-Identifier: Apache-2.0
Author: Yachay (CTO authority) - Built by Perplexity Computer Agent - 2026-06-03
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from .governance import (
    DsseSigner,
    KhipuChain,
    YUYAY_FLOORS,
    hatun_mcp_factor,
    hukla_check,
    puriq_utility,
    yuyay_gate,
)

# The 12-organ runtime (v21 PURIQ-OS). Default quorum set when caller gives none.
# Honest organ role names (the purged sentra/rosie/amaru backends are now served
# by the live a11oy immune/companion/llm organs).
DEFAULT_ORGANS = [
    "a11oy", "killinchu", "immune", "companion", "llm", "wayra",
    "yachay", "hatun", "wallpa", "unay", "chaski", "wasi-rikuq",
]


def mesh_quorum(organ_ids: list[str], present: Optional[list[str]] = None) -> dict:
    """Byzantine quorum: with n organs the system tolerates f = floor((n-1)/3)
    faults and needs a threshold of 2f+1 present to reach quorum (n >= 3f+1).

    REAL quorum arithmetic. Live cluster polling is the disclosed boundary: when no
    `present` list is supplied we treat all organs as present (in-proc default), and
    mark `live_polled=False` so the caller never mistakes this for a cluster probe.
    """
    organs = list(dict.fromkeys(organ_ids or DEFAULT_ORGANS))  # de-dup, keep order
    n = len(organs)
    f = max(0, (n - 1) // 3)
    threshold = 2 * f + 1
    live_polled = present is not None
    present_set = list(present) if present is not None else list(organs)
    present_count = len([o for o in present_set if o in organs])
    return {
        "n": n,
        "f": f,
        "threshold": threshold,
        "present": present_set,
        "present_count": present_count,
        "quorum": present_count >= threshold and n >= (3 * f + 1),
        "live_polled": live_polled,
        "note": (
            "Byzantine n>=3f+1; threshold=2f+1. live_polled=false means present set "
            "defaulted to all organs (in-proc), not a real cluster probe."
        ),
    }


def yuyay_verdict(min_axis_value: float, passed: bool) -> str:
    """PASS / AMBER / FAIL overlay (operational; does not weaken the gate)."""
    if not passed:
        return "FAIL"
    if min_axis_value >= 0.95:
        return "PASS"
    return "AMBER"  # passes all floors but weakest structural axis is in [0.90, 0.95)


def puriq_master(
    input: Any,
    context: Optional[dict] = None,
    *,
    organs: Optional[list[str]] = None,
    khipu: Optional[KhipuChain] = None,
    signer: Optional[DsseSigner] = None,
    reputation: float = 0.7,
    authenticated: bool = True,
    scope_ok: bool = True,
    state_changing: bool = False,
    two_person: bool = False,
) -> dict:
    """THE named PURIQ entrypoint.

    Returns the operational triple plus the full factor breakdown:
        {
          "Lambda": float in [0,1],          # composed master-formula scalar u(a)
          "receipts": [ {continuum_hash, prev_hash, dsse, ...} ],
          "traceparent": "00-<trace>-<span>-01",  # W3C traceparent
          "axes": { ... 13 Yuyay axis scores ... },
          "verdict": "PASS" | "AMBER" | "FAIL",
          "quorum": { n, f, threshold, present, quorum },
        }
    """
    context = context or {}
    khipu = khipu if khipu is not None else KhipuChain()
    signer = signer if signer is not None else DsseSigner()

    gate_text = input if isinstance(input, str) else _stringify(input)

    # 1. Yuyay-13 gate (real).
    yz = yuyay_gate(gate_text)
    verdict = yuyay_verdict(yz.min_axis_value, yz.passed)

    # 2. Mesh quorum over organs (real arithmetic).
    present = context.get("present_organs")
    quorum = mesh_quorum(organs or DEFAULT_ORGANS, present)

    # 3. Hatun_MCP factor (authz x reputation x dual-control).
    factor = hatun_mcp_factor(
        authenticated=authenticated, scope_ok=scope_ok, reputation=reputation,
        state_changing=state_changing, two_person=two_person,
    )

    # 4. Chain integrity BEFORE append, then HUKLLA.
    chain_ok = khipu.verify()
    tripwire = hukla_check(
        chain_ok=chain_ok, yuyay=yz, latency_s=0.0,
        latency_budget_s=5.0, action_space=1,
    )

    # 5. Master-formula scalar u(a) in [0,1] (Lambda input = 1.0; real composition).
    lam_input = float(context.get("lambda", 1.0))
    lam_input = max(0.0, min(1.0, lam_input))
    score = puriq_utility(
        lam=lam_input, yuyay=yz, hukla_tripwire=tripwire,
        khipu_chain_ok=chain_ok, hatun_factor=factor,
    )

    # 6. Khipu append (one link) + DSSE-sign.
    status = "success" if yz.passed and quorum["quorum"] else "declined"
    receipt = khipu.emit(
        tool="puriq_master",
        client_id=str(context.get("client_id", "puriq")),
        operation_id="puriq.master",
        status=status,
        tripwire=tripwire,
        yuyay_min_axis=yz.min_axis_value,
        hatun_mcp_factor=factor,
        puriq_score=score,
        detail={
            "verdict": verdict,
            "quorum": quorum,
            "lambda_input": lam_input,
            "context_keys": sorted(context.keys()),
        },
        signer=signer,
    )

    trace = uuid.uuid4().hex
    span = uuid.uuid4().hex[:16]
    traceparent = f"00-{trace}-{span}-01"

    return {
        "Lambda": score,
        "receipts": [{
            "receipt_id": receipt.receipt_id,
            "continuum_hash": receipt.continuum_hash,
            "prev_hash": receipt.prev_hash,
            "status": receipt.status,
            "tripwire": receipt.tripwire,
            "dsse": receipt.dsse,
            "chain_verified": khipu.verify(),
        }],
        "traceparent": traceparent,
        "axes": yz.scores,
        "verdict": verdict,
        "quorum": quorum,
        "signer_mode": signer.mode,
        "floors": YUYAY_FLOORS,
    }


def _stringify(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, sort_keys=True, default=str)[:200_000]
    except Exception:
        return str(obj)[:200_000]
