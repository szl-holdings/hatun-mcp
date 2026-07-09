"""hatun_mcp.loop — the Ouroboros bounded loop kernel (IN CODE, receipt-closed).

Doctrine cross-reference: the canonical receipt-closed kernel is
szl-holdings/ouroboros → src/loop-kernel.ts (`runLoop`): *bounded recursion with
measurable convergence* that MUST terminate on one of a fixed set of exit
conditions and emits a governance receipt for every run. **The trace is the
product.**

This module makes that primitive REAL on this repo's actual multi-step
orchestration path — the Byzantine Λ-quorum fan-out in
`hatun_mcp.server.szl_lambda_quorum`, which walks a caller-supplyable list of
organs. Previously that walk had no hard step cap; this kernel wraps it with:

  * a HARD step budget from env/config with a safe default,
  * per-step trace entries (`LoopStep`: n / type / label),
  * an HONEST exit reason — ``converged`` | ``budget_exhausted`` | ``error`` —
    surfaced in the response/receipt/log output, never a fabricated convergence.

Honesty (Doctrine v11 · Λ = Conjecture 1): this is a *bounded, terminating* loop.
It makes NO perpetual-motion / zero-cost / free-energy claim. ``converged`` is
emitted ONLY when the finite walk actually completed within budget (or a caller's
convergence predicate is really satisfied) — if the hard budget is hit first the
exit is ``budget_exhausted`` (disclosed, not forced).

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

# ── Fixed exit vocabulary — honest, never fake convergence ───────────────────────
EXIT_CONVERGED = "converged"
EXIT_BUDGET_EXHAUSTED = "budget_exhausted"
EXIT_ERROR = "error"

# The doctrine line carried on every trace (mirrors the reference LoopTrace).
DOCTRINE_LINE = "bounded, terminating, receipt-closed"

# Env-configurable hard cap with a safe default. The default (12) comfortably
# covers the 12-organ PURIQ-OS runtime and the 5-organ default quorum set, so
# DEFAULT BEHAVIOR IS UNCHANGED unless a caller supplies more steps than the cap.
DEFAULT_MAX_STEPS = 12
_ENV_MAX_STEPS = "HATUN_MCP_LOOP_MAX_STEPS"


def loop_max_steps(override: Optional[int] = None) -> int:
    """Resolve the hard step budget: explicit override > env > safe default.

    Always returns a strictly-positive int. A non-positive / unparseable override
    or env value falls back to the safe default — FAIL-SAFE, never an unbounded or
    zero budget (a zero/negative budget would either process nothing or, worse,
    disable the cap).
    """
    if override is not None:
        try:
            v = int(override)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    raw = os.environ.get(_ENV_MAX_STEPS)
    if raw is not None:
        try:
            v = int(raw)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return DEFAULT_MAX_STEPS


@dataclass
class LoopStep:
    """One compact entry in the Ouroboros per-step trace (the trace is the product).

    `type` mirrors the reference LoopStepType vocabulary:
    system | network | action | success | output | error.
    """

    n: int
    type: str
    label: str

    def to_dict(self) -> dict:
        return {"n": self.n, "type": self.type, "label": self.label}


@dataclass
class LoopTrace:
    """Ouroboros loop block — bounded, terminating, receipt-closed.

    `doctrine` is a DOCTRINE label (doctrine-not-math, never a proof); it cross-refs
    szl-holdings/ouroboros runLoop.
    """

    max_budget: int = DEFAULT_MAX_STEPS
    exit: str = EXIT_BUDGET_EXHAUSTED
    trace: list = field(default_factory=list)
    doctrine: str = DOCTRINE_LINE
    iterations: int = 0

    def add(self, type: str, label: str) -> None:
        """Record one honest trace entry."""
        self.trace.append(LoopStep(n=len(self.trace) + 1, type=type, label=label))

    def to_dict(self) -> dict:
        return {
            # `steps` = loop iterations actually executed (bounded).
            "steps": self.iterations,
            "maxBudget": self.max_budget,
            "exit": self.exit,
            "trace": [s.to_dict() for s in self.trace],
            "doctrine": self.doctrine,
        }


async def run_bounded_loop(
    items: list,
    step_fn: Callable[[int, Any, "LoopTrace"], Awaitable[Any]],
    *,
    max_steps: Optional[int] = None,
    converged: Optional[Callable[[list], bool]] = None,
):
    """Run ``step_fn`` over ``items`` inside a HARD-bounded Ouroboros loop.

    Returns ``(results, trace)`` where ``trace`` is a :class:`LoopTrace`. The
    ``trace.exit`` is one of:

      * ``"converged"``        — the finite walk completed within budget, or the
        caller's ``converged(results)`` predicate really returned True. This is a
        real terminating fixpoint, NEVER a fabricated one.
      * ``"budget_exhausted"`` — the hard step budget was reached before all items
        were processed (disclosed, not forced; remaining items are NOT dropped
        silently — the miss is recorded in the trace).
      * ``"error"``            — a step raised; the error is recorded and the loop
        stops (honest error exit).

    Bounded & terminating: at most ``max_steps`` iterations run regardless of how
    many items are supplied, so no unbounded walk is left on the path.
    """
    budget = loop_max_steps(max_steps)
    trace = LoopTrace(max_budget=budget)
    trace.add("system", f"loop start: {len(items)} item(s); hard budget={budget}")
    results: list = []

    for idx, item in enumerate(items):
        if trace.iterations >= budget:
            trace.exit = EXIT_BUDGET_EXHAUSTED
            trace.add(
                "output",
                f"budget exhausted at {trace.iterations}/{budget}; "
                f"{len(items) - idx} item(s) not processed (disclosed, not forced)",
            )
            return results, trace

        trace.iterations += 1
        try:
            res = await step_fn(idx, item, trace)
            results.append(res)
            trace.add("success", f"step {trace.iterations}/{len(items)} completed")
        except Exception as e:  # honest error exit — loop stops, disclosed
            trace.exit = EXIT_ERROR
            trace.add("error", f"step {idx} raised {type(e).__name__}: {e}")
            return results, trace

        if converged is not None and converged(results):
            trace.exit = EXIT_CONVERGED
            trace.add(
                "success",
                f"convergence predicate satisfied at step {trace.iterations}",
            )
            return results, trace

    trace.exit = EXIT_CONVERGED
    trace.add(
        "output",
        f"all {len(results)} item(s) processed within budget; loop terminated",
    )
    return results, trace
