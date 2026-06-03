"""hatun_mcp.tools.governance_tools — five governance gates as first-class MCP tools.

Wraps the REAL primitives in hatun_mcp.governance (yuyay_gate, KhipuChain, DsseSigner,
the Byzantine mesh-quorum arithmetic, and the PAC-Bayes bound) and the puriq_master
orchestrator. Each tool emits / verifies a Khipu receipt and returns a DSSE-signed,
JSON-serializable response per the server's 7-step contract.

Honest interface contract:
  * mesh_quorum_status returns REAL n>=3f+1 arithmetic; live cluster polling is the
    disclosed boundary (live_polled=false unless a `present` set is supplied).
  * dsse_sign returns honesty="REAL" only when a signing key is present in the env;
    otherwise honesty="UNSIGNED" with an empty signatures[] (disclosed, never faked).

Kept under 300 LOC. SPDX-License-Identifier: Apache-2.0
Author: Yachay (CTO authority) - Built by Perplexity Computer Agent - 2026-06-03
"""
from __future__ import annotations

import math
from typing import Any, Optional

from ..governance import (
    DsseSigner,
    KhipuChain,
    YUYAY_FLOORS,
    yuyay_gate,
)
from ..puriq import mesh_quorum, puriq_master, yuyay_verdict


def pacbayes_bound(emp_risk: float, kl: float, n: int, delta: float) -> float:
    """Published PAC-Bayes (McAllester-style) generalization bound:

        R(Q) <= emp_risk + sqrt( (KL(Q||P) + ln(2*sqrt(n)/delta)) / (2*n) )

    REAL closed-form arithmetic; inputs are caller-supplied (honest). Traces to
    lutar-lean PACBayes/PACBayes.lean::pacBayesBound + pacBayes_inequality_form.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not (0.0 < delta < 1.0):
        raise ValueError("delta must be in (0,1)")
    if kl < 0:
        raise ValueError("kl must be >= 0")
    slack = math.sqrt((kl + math.log(2.0 * math.sqrt(n) / delta)) / (2.0 * n))
    return emp_risk + slack


def _install(mcp, khipu: KhipuChain, signer: DsseSigner, clients) -> None:
    """Register the five tools on the shared FastMCP instance, reusing live state."""

    @mcp.tool()
    async def yuyay_gate_check(input: str, axes_to_run: Optional[list] = None) -> dict:
        """Run the 13-axis Yuyay gate over `input` (input-as-data defense).

        Returns the per-axis verdicts, the Lambda contribution (0/1 conjunctive AND),
        and a Khipu receipt. axes_to_run optionally restricts which axes are reported
        (the gate itself always evaluates all 13; this only filters the report).
        """
        yz = yuyay_gate(input or "")
        verdict = yuyay_verdict(yz.min_axis_value, yz.passed)
        scores = yz.scores
        if axes_to_run:
            scores = {a: v for a, v in scores.items() if a in set(axes_to_run)}
        verdicts = [
            {"axis": a, "score": yz.scores[a], "floor": YUYAY_FLOORS[a],
             "ok": yz.scores[a] >= YUYAY_FLOORS[a]}
            for a in scores
        ]
        lam = 1.0 if yz.passed else 0.0
        r = khipu.emit(
            tool="yuyay_gate_check", client_id="mcp", operation_id="yuyay.gate.check",
            status="success" if yz.passed else "declined",
            tripwire=None if yz.passed else "T09",
            yuyay_min_axis=yz.min_axis_value, hatun_mcp_factor=1.0,
            puriq_score=lam, detail={"verdict": verdict, "blocked_axis": yz.blocked_axis},
            signer=signer,
        )
        return {
            "verdicts": verdicts,
            "passed": yz.passed,
            "verdict": verdict,
            "blocked_axis": yz.blocked_axis,
            "min_axis": {"name": yz.min_axis_name, "value": yz.min_axis_value},
            "lambda": lam,
            "receipt": {"continuum_hash": r.continuum_hash, "prev_hash": r.prev_hash,
                        "chain_verified": khipu.verify()},
        }

    @mcp.tool()
    async def khipu_append_and_verify(payload: dict, parent_hash: Optional[str] = None) -> dict:
        """Append one Khipu link carrying `payload` and recompute-verify the chain.

        parent_hash is advisory (the live chain links to its own last hash); when
        supplied and it does not match the live tip, we disclose the mismatch.
        """
        live_tip = khipu._last_hash  # noqa: SLF001 - intentional read of live tip
        tip_match = (parent_hash is None) or (parent_hash == live_tip)
        r = khipu.emit(
            tool="khipu_append_and_verify", client_id="mcp",
            operation_id="khipu.append", status="success", tripwire=None,
            yuyay_min_axis=None, hatun_mcp_factor=1.0, puriq_score=1.0,
            detail={"payload": payload, "parent_hash_supplied": parent_hash,
                    "parent_hash_matched_tip": tip_match},
            signer=signer,
        )
        verified = khipu.verify()
        return {
            "hash": r.continuum_hash,
            "prev_hash": r.prev_hash,
            "dsse": r.dsse,
            "verified": verified,
            "parent_hash_matched_tip": tip_match,
        }

    @mcp.tool()
    async def dsse_sign(payload: dict, key_env_var: str = "SZL_COSIGN_PRIVATE_PEM") -> dict:
        """Sign `payload` with a real ECDSA P-256 DSSE envelope.

        Uses the server's live signer (loaded from HATUN_MCP_SIGNING_KEY). When no key
        is present in this process, returns honesty='UNSIGNED' with an empty
        signatures[] (disclosed, never faked). key_env_var documents which env var the
        Cosign Bootstrap squad will populate (SZL_COSIGN_PRIVATE_PEM).
        """
        env = signer.sign(payload)
        signed = bool(env.get("signatures"))
        return {
            "envelope": env,
            "honesty": "REAL" if signed else "UNSIGNED",
            "signer_mode": signer.mode,
            "key_env_var": key_env_var,
            "note": (
                "Real ECDSA P-256 over DSSE PAE."
                if signed else
                f"No signing key in process; set {key_env_var} (Cosign Bootstrap) "
                "to produce real signatures. Disclosed, not faked."
            ),
        }

    @mcp.tool()
    async def mesh_quorum_status(organ_ids: list, present: Optional[list] = None) -> dict:
        """Byzantine n>=3f+1 mesh-quorum status over the named organs.

        Returns n, f, threshold (=2f+1), present set, and the quorum boolean. Live
        cluster polling is the disclosed boundary (live_polled=false when `present`
        is omitted). Traces to lutar-lean KhipuConsensus.lean::khipu_consensus_safety.
        """
        q = mesh_quorum(list(organ_ids or []), present)
        khipu.emit(
            tool="mesh_quorum_status", client_id="mcp", operation_id="mesh.quorum",
            status="success", tripwire=None, yuyay_min_axis=None,
            hatun_mcp_factor=1.0, puriq_score=1.0, detail={"quorum": q}, signer=signer,
        )
        return q

    @mcp.tool()
    async def puriq_master_tool(input: str, context: Optional[dict] = None) -> dict:
        """THE named PURIQ entrypoint over MCP.

        PURIQ(input, context) -> (Lambda in [0,1], DSSE-signed Khipu receipt,
        traceparent chain, 13-axis breakdown). Composes Yuyay-13 -> quorum -> HUKLLA
        -> Khipu append -> DSSE-sign using the server's LIVE chain + signer.
        """
        ctx = dict(context or {})
        out = puriq_master(
            input, ctx, khipu=khipu, signer=signer,
            reputation=float(ctx.get("reputation", 0.7)),
            state_changing=bool(ctx.get("state_changing", False)),
            two_person=bool(ctx.get("two_person", False)),
        )
        return {
            "Lambda": out["Lambda"],
            "receipts": out["receipts"],
            "traceparent": out["traceparent"],
            "axes": out["axes"],
            "verdict": out["verdict"],
            "quorum": out["quorum"],
            "signer_mode": out["signer_mode"],
        }

    # Sixth registration: the PAC-Bayes bound (F7), exposed as a pure-arithmetic tool.
    @mcp.tool()
    async def governance_pacbayes_bound(emp_risk: float, kl: float, n: int,
                                        delta: float = 0.05) -> dict:
        """Compute the published PAC-Bayes governance-ensemble bound (F7).

        REAL closed-form; inputs caller-supplied. Emits a Khipu receipt.
        """
        bound = pacbayes_bound(emp_risk, kl, n, delta)
        r = khipu.emit(
            tool="governance_pacbayes_bound", client_id="mcp",
            operation_id="pacbayes.bound", status="success", tripwire=None,
            yuyay_min_axis=None, hatun_mcp_factor=1.0, puriq_score=1.0,
            detail={"emp_risk": emp_risk, "kl": kl, "n": n, "delta": delta,
                    "bound": bound},
            signer=signer,
        )
        return {"bound": bound, "inputs": {"emp_risk": emp_risk, "kl": kl, "n": n,
                "delta": delta},
                "receipt": {"continuum_hash": r.continuum_hash}}
