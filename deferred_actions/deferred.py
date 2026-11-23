"""Deferred-action staleness contracts on a CPU-only executor (propose-only).

Doctrine (leader-study card r1): deferred tool calls carry explicit
staleness contracts - defer time, expiry, and stale-handling - declared
up front; EXPIRED work is rejected BEFORE execution, not after; a
recheck hook may confirm an action is still wanted at execution time;
the executor is CPU-only and the witness loop only ever reads registered
state, never blocks.

Honest limitation, disclosed: run callables are contractually
non-blocking and CPU-bound; this contract is NOT enforceable at runtime
in pure Python - a misbehaving blocking callable cannot be detected,
only disclosed by contract.

PROPOSAL_ONLY, unsigned; merges are owned by the estate signature wall.
No status claims are made about any other pull request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

REJECT = "reject"
RECHECK = "recheck"

STALE_POLICIES = (REJECT, RECHECK)


class ContractError(ValueError):
    """A deferred-action staleness contract is malformed."""


@dataclass
class DeferredAction:
    """A deferred tool call plus its staleness contract."""

    action_id: str
    requested_at: float
    expires_after_s: float
    stale_policy: str = REJECT
    recheck: Optional[Callable[[], bool]] = None
    run: Optional[Callable[[], object]] = None

    def __post_init__(self):
        if not self.action_id or not isinstance(self.action_id, str):
            raise ContractError("action_id must be a non-empty string")
        if self.expires_after_s <= 0:
            raise ContractError("expires_after_s must be positive")
        if self.stale_policy not in STALE_POLICIES:
            raise ContractError("stale_policy must be one of %s" % (STALE_POLICIES,))
        if self.stale_policy == RECHECK and self.recheck is None:
            raise ContractError("recheck policy requires a recheck callable")

    def is_expired(self, now_ts: float) -> bool:
        return now_ts >= self.requested_at + self.expires_after_s

    def expires_at(self) -> float:
        return self.requested_at + self.expires_after_s


@dataclass
class DeferredDecision:
    action_id: str
    executed: bool
    reason: str
    stale: bool = False
    elapsed_s: float = 0.0
    result: object = None

    def as_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "executed": self.executed,
            "stale": self.stale,
            "reason": self.reason,
            "elapsed_s": self.elapsed_s,
            "result": self.result if isinstance(self.result, (int, float, str, bool, type(None))) else "<opaque>",
        }


class CPUOnlyExecutor:
    """Registers, staleness-checks, and runs deferred actions.

    The witness reads registered state only (in_flight / completed
    counts) so a misbehaving action cannot stall the witness loop.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._in_flight: Dict[str, DeferredAction] = {}
        self._completed: List[str] = []

    def witness_in_flight(self) -> int:
        return len(self._in_flight)

    def witness_completed(self) -> int:
        return len(self._completed)

    def staleness_check(self, action: DeferredAction, now_ts: float):
        """Return (stale, reason); never runs the action."""
        if not isinstance(action, DeferredAction):
            raise ContractError("staleness_check requires a DeferredAction")
        if action.is_expired(now_ts):
            return (True, "expired %.3fs ago: stale contract rejects before run" %
                    (now_ts - action.expires_at()))
        if action.stale_policy == RECHECK and action.recheck() is not True:
            return (True, "recheck hook returned non-True: action no longer wanted")
        return (False, "within staleness contract")

    def execute(self, action: DeferredAction, now_ts: Optional[float] = None):
        """Staleness-check first (fail closed), then run once."""
        now = self.clock() if now_ts is None else float(now_ts)
        stale, reason = self.staleness_check(action, now)
        if stale:
            return DeferredDecision(action_id=action.action_id, executed=False,
                                    stale=True, reason=reason)
        self._in_flight[action.action_id] = action
        started = self.clock()
        result = None
        error = None
        try:
            if action.run is not None:
                result = action.run()
        except Exception as exc:
            error = "%s: %s" % (type(exc).__name__, exc)
        finally:
            elapsed = self.clock() - started
            self._in_flight.pop(action.action_id, None)
            self._completed.append(action.action_id)
        final_reason = "executed" if error is None else ("run raised " + error)
        return DeferredDecision(action_id=action.action_id, executed=True, stale=False,
                                 reason=final_reason, elapsed_s=elapsed, result=result)
