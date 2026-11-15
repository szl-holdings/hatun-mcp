"""hatun_mcp.tools.axle_bridge — AxiomMath's AXLE MCP surface, consolidated
under SZL doctrine as SECONDARY-oracle tools.

Consolidates ALL 16 AXLE endpoints (verify_proof, check, extract_decls,
extract_proof_states, sorry2lemma, repair_proofs, disprove, merge, rename,
theorem2lemma, theorem2sorry, have2lemma, have2sorry, simplify_theorems,
normalize, extract_theorems) into eight static hatun tools. Every call runs
through the full PURIQ pipeline (governed(): auth, Yuyay-13 gate on input,
reputation, latency budget, Khipu receipt on success AND failure, DSSE).

The SZL tweaks over a plain mirror (instill decision 2026-11-15):
  * SECONDARY ORACLE: results corroborate; they never authorize. The estate's
    local Lean kernel (szl_lean_verify) stays the authorizing oracle.
  * FAIL-CLOSED ABSTAIN: no key / unreachable / non-200 => an honest
    abstain receipt, never a pass.
  * Strict-by-default verification: permitted_sorries defaults to none;
    verify_negation is opt-in and its outcome is surfaced, never hidden.
  * Fixed allowlist, no redirects, bounded I/O, key never echoed (see
    hatun_mcp.axle for the full trust boundary).

SPDX-License-Identifier: Apache-2.0
Author: SZL Holdings — AXLE bridge (instill decision 2026-11-15)
"""
from __future__ import annotations

from typing import Any, Optional

from .. import axle as A


def _install(mcp, khipu, signer, clients) -> None:
    """Register the eight AXLE bridge tools on the shared FastMCP instance,
    reusing live governance state. Lazy-imports governed() from the server
    module (which is already fully initialized at registration time)."""
    from ..server import governed  # lazy: no import-time cycle

    @mcp.tool()
    async def szl_axle_status() -> dict:
        """AXLE secondary-oracle health probe (GET /v1/status).

        Corroboration infrastructure check only: it never authorizes
        anything, and an unreachable AXLE is an honest abstain, never a pass.
        The estate's local Lean kernel remains the authorizing oracle."""
        return await governed(
            tool="szl_axle_status", operation_id="axle.status",
            gate_text="AXLE secondary-oracle health probe",
            needs_scope="read", latency_budget=A.AXLE_STATUS_TIMEOUT_SECONDS + 10.0,
            backend_coro=A.axle_get("status"),
        )

    @mcp.tool()
    async def szl_axle_environments() -> dict:
        """List AXLE's managed Lean environments (GET /v1/environments).

        Secondary oracle: informs which pinned environment a corroborating
        call will run in. It never authorizes; the local kernel stays primary."""
        return await governed(
            tool="szl_axle_environments", operation_id="axle.environments",
            gate_text="AXLE managed Lean environment list",
            needs_scope="read", latency_budget=A.AXLE_STATUS_TIMEOUT_SECONDS + 10.0,
            backend_coro=A.axle_get("environments"),
        )

    @mcp.tool()
    async def szl_axle_verify_proof(
        formal_statement: str, content: str, environment: str,
        permitted_sorries: Optional[list] = None,
        verify_negation: bool = False,
        timeout_seconds: Optional[float] = None,
    ) -> dict:
        """Verify a candidate Lean proof against a formal statement, as a
        SECONDARY oracle (POST api/v1/verify_proof).

        SZL tweaks over the raw AXLE tool: strict by default (permitted_sorries
        defaults to NONE — a proof with any sorry does not corroborate);
        verify_negation is explicit opt-in; the pinned `environment` is always
        named so environment drift is receipted. The result corroborates only:
        the estate's local kernel (szl_lean_verify) authorizes, and this is
        not human review. Fail-closed: no key / unreachable => honest abstain."""
        payload: dict[str, Any] = {
            "formal_statement": formal_statement, "content": content,
            "environment": environment,
            "verify_negation": bool(verify_negation),
        }
        if permitted_sorries is not None:
            payload["permitted_sorries"] = list(permitted_sorries)
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        return await governed(
            tool="szl_axle_verify_proof", operation_id="axle.verify_proof",
            gate_text=f"{formal_statement}\n{content}",
            needs_scope="read", latency_budget=A._budget(payload.get("timeout_seconds")),
            backend_coro=A.axle_run("verify_proof", payload),
        )

    @mcp.tool()
    async def szl_axle_check(content: str, environment: str,
                             timeout_seconds: Optional[float] = None) -> dict:
        """Check Lean code for errors, as a SECONDARY oracle (POST api/v1/check).

        Sorry/axiom findings are warnings in AXLE's `okay`; the estate surfaces
        the raw verdict and classifies only corroborated / not_corroborated /
        abstain. It never authorizes; the local kernel stays primary."""
        payload = {"content": content, "environment": environment}
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        return await governed(
            tool="szl_axle_check", operation_id="axle.check",
            gate_text=content, needs_scope="read",
            latency_budget=A._budget(payload.get("timeout_seconds")),
            backend_coro=A.axle_run("check", payload),
        )

    @mcp.tool()
    async def szl_axle_disprove(content: str, environment: str,
                               timeout_seconds: Optional[float] = None) -> dict:
        """Attempt to DISPROVE theorems, as a SECONDARY oracle
        (POST api/v1/disprove).

        Aligned with PROOF/ABSTAIN doctrine: a successful AXLE disproof of an
        estate claim must be visible immediately — an adversarial probe is
        evidence, never a rubber stamp. Fail-closed abstain when unreachable."""
        payload = {"content": content, "environment": environment}
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        return await governed(
            tool="szl_axle_disprove", operation_id="axle.disprove",
            gate_text=content, needs_scope="read",
            latency_budget=A._budget(payload.get("timeout_seconds")),
            backend_coro=A.axle_run("disprove", payload),
        )

    @mcp.tool()
    async def szl_axle_sorry2lemma(content: str, environment: str,
                                   names: Optional[list] = None,
                                   timeout_seconds: Optional[float] = None) -> dict:
        """Extract every `sorry` (and elaboration error) into standalone named
        lemma targets (POST api/v1/sorry2lemma).

        The sorry-gate ratchet hook: turns open sorries into named proof-state
        targets the estate's self-proving lanes can attack. Secondary oracle:
        the extracted targets corroborate; the local kernel authorizes their
        discharge."""
        payload: dict[str, Any] = {"content": content, "environment": environment}
        if names is not None:
            payload["names"] = list(names)
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        return await governed(
            tool="szl_axle_sorry2lemma", operation_id="axle.sorry2lemma",
            gate_text=content, needs_scope="read",
            latency_budget=A._budget(payload.get("timeout_seconds")),
            backend_coro=A.axle_run("sorry2lemma", payload),
        )

    @mcp.tool()
    async def szl_axle_extract_proof_states(content: str, environment: str,
                                            timeout_seconds: Optional[float] = None
                                            ) -> dict:
        """Extract the proof state at each line of Lean code
        (POST api/v1/extract_proof_states).

        Feeds the estate's self-proving Salad lanes proof STATES, not whole
        files (instill Tier 1). Secondary oracle: the states corroborate; the
        local kernel authorizes any discharge."""
        payload = {"content": content, "environment": environment}
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        return await governed(
            tool="szl_axle_extract_proof_states",
            operation_id="axle.extract_proof_states",
            gate_text=content, needs_scope="read",
            latency_budget=A._budget(payload.get("timeout_seconds")),
            backend_coro=A.axle_run("extract_proof_states", payload),
        )

    @mcp.tool()
    async def szl_axle_call(endpoint: str, payload: dict) -> dict:
        """Consolidated allowlisted passthrough for ANY of the 16 AXLE
        endpoints (POST api/v1/<endpoint>).

        `endpoint` must be one of the fixed allowlist (verify_proof, check,
        extract_decls, extract_proof_states, sorry2lemma, disprove, merge,
        normalize, rename, theorem2lemma, theorem2sorry, have2lemma,
        have2sorry, simplify_theorems, repair_proofs, extract_theorems);
        `payload` is the AXLE request body (content/environment/...). Anything
        not on the allowlist is declined before any network call. Secondary
        oracle: corroborates, never authorizes; fail-closed abstain."""
        if endpoint not in A.AXLE_ENDPOINTS:
            import json as _json
            return await governed(
                tool="szl_axle_call", operation_id="axle.call",
                gate_text=_json.dumps({"endpoint": endpoint})[:2000],
                needs_scope="read",
                backend_coro=A.axle_run(endpoint, {}),
            )
        import json as _json
        return await governed(
            tool="szl_axle_call", operation_id=f"axle.{endpoint}",
            gate_text=_json.dumps({"endpoint": endpoint, "payload": payload})[:8000],
            needs_scope="read", latency_budget=A._budget((payload or {}).get("timeout_seconds")),
            backend_coro=A.axle_run(endpoint, payload),
        )
