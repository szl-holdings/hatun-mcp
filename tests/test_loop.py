"""Ouroboros bounded loop kernel — hermetic tests (no network, no live organs).

Exercises `hatun_mcp.loop`: the hard step budget (env/override/safe-default), the
per-step honest trace, and the honest exit vocabulary
(converged | budget_exhausted | error). `converged` is asserted to be emitted ONLY
when the finite walk really completes (or a predicate is really satisfied) — never
fabricated; hitting the hard cap first must surface `budget_exhausted`.

Async is driven with asyncio.run(...) (matching tests/test_adapters.py), so this
suite needs no pytest-asyncio markers.

SPDX-License-Identifier: Apache-2.0
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hatun_mcp.loop import (  # noqa: E402
    DEFAULT_MAX_STEPS,
    EXIT_BUDGET_EXHAUSTED,
    EXIT_CONVERGED,
    EXIT_ERROR,
    LoopTrace,
    loop_max_steps,
    run_bounded_loop,
)


def _run(items, step_fn, **kw):
    return asyncio.run(run_bounded_loop(items, step_fn, **kw))


async def _identity_step(idx, item, trace):
    return item


def test_loop_max_steps_default_and_override():
    prev = os.environ.pop("HATUN_MCP_LOOP_MAX_STEPS", None)
    try:
        assert loop_max_steps() == DEFAULT_MAX_STEPS
        assert loop_max_steps(3) == 3
        # non-positive / unparseable override falls back to safe default (fail-safe)
        assert loop_max_steps(0) == DEFAULT_MAX_STEPS
        assert loop_max_steps(-5) == DEFAULT_MAX_STEPS
    finally:
        if prev is not None:
            os.environ["HATUN_MCP_LOOP_MAX_STEPS"] = prev


def test_loop_max_steps_from_env():
    prev = os.environ.get("HATUN_MCP_LOOP_MAX_STEPS")
    try:
        os.environ["HATUN_MCP_LOOP_MAX_STEPS"] = "7"
        assert loop_max_steps() == 7
        # explicit override beats env
        assert loop_max_steps(2) == 2
        # unparseable / non-positive env falls back to safe default (never unbounded)
        os.environ["HATUN_MCP_LOOP_MAX_STEPS"] = "not-a-number"
        assert loop_max_steps() == DEFAULT_MAX_STEPS
        os.environ["HATUN_MCP_LOOP_MAX_STEPS"] = "0"
        assert loop_max_steps() == DEFAULT_MAX_STEPS
    finally:
        if prev is None:
            os.environ.pop("HATUN_MCP_LOOP_MAX_STEPS", None)
        else:
            os.environ["HATUN_MCP_LOOP_MAX_STEPS"] = prev


def test_all_items_within_budget_exits_converged():
    results, trace = _run(["a", "b", "c"], _identity_step, max_steps=12)
    assert results == ["a", "b", "c"]
    assert trace.exit == EXIT_CONVERGED
    assert trace.iterations == 3
    d = trace.to_dict()
    assert d["steps"] == 3
    assert d["maxBudget"] == 12
    assert d["exit"] == "converged"
    assert d["doctrine"] == "bounded, terminating, receipt-closed"
    # honest trace present: a start (system) entry + the per-step entries + final output
    assert d["trace"][0]["type"] == "system"
    assert d["trace"][-1]["type"] == "output"
    assert all(set(e) == {"n", "type", "label"} for e in d["trace"])


def test_budget_exhausted_is_honest_not_faked_convergence():
    # 5 items, hard budget 3 -> only 3 processed, exit budget_exhausted (NOT converged).
    results, trace = _run(["a", "b", "c", "d", "e"], _identity_step, max_steps=3)
    assert trace.exit == EXIT_BUDGET_EXHAUSTED
    assert trace.exit != EXIT_CONVERGED  # never fake convergence when capped
    assert trace.iterations == 3
    assert results == ["a", "b", "c"]  # remaining items not silently dropped-as-done
    d = trace.to_dict()
    assert d["steps"] == 3
    # the miss is disclosed in the trace, not forced
    assert any("budget exhausted" in e["label"] for e in d["trace"])


def test_exactly_at_budget_boundary_converges():
    # items == budget: the finite walk completes -> converged.
    results, trace = _run(["a", "b", "c"], _identity_step, max_steps=3)
    assert trace.exit == EXIT_CONVERGED
    assert trace.iterations == 3
    assert results == ["a", "b", "c"]


def test_error_step_exits_error_and_stops():
    async def _boom(idx, item, trace):
        if idx == 1:
            raise ValueError("organ blew up")
        return item

    results, trace = _run(["a", "b", "c"], _boom, max_steps=12)
    assert trace.exit == EXIT_ERROR
    assert results == ["a"]  # stopped at the failing step
    assert trace.iterations == 2  # started step 2, which raised
    d = trace.to_dict()
    assert any(e["type"] == "error" and "ValueError" in e["label"] for e in d["trace"])


def test_convergence_predicate_exits_early_when_really_satisfied():
    # Stop as soon as we've collected a "GO" — real convergence, recorded honestly.
    async def _step(idx, item, trace):
        return item

    def _converged(results):
        return "GO" in results

    results, trace = _run(["x", "GO", "y", "z"], _step, max_steps=12,
                          converged=_converged)
    assert trace.exit == EXIT_CONVERGED
    assert results == ["x", "GO"]
    assert trace.iterations == 2
    assert any("convergence predicate satisfied" in e["label"]
               for e in trace.to_dict()["trace"])


def test_empty_items_terminates_converged():
    results, trace = _run([], _identity_step, max_steps=5)
    assert results == []
    assert trace.exit == EXIT_CONVERGED
    assert trace.iterations == 0


def test_trace_step_numbers_are_monotonic():
    _, trace = _run(["a", "b"], _identity_step, max_steps=12)
    ns = [e["n"] for e in trace.to_dict()["trace"]]
    assert ns == list(range(1, len(ns) + 1))


def test_loop_trace_default_exit_is_honest():
    # A fresh trace defaults to budget_exhausted (never optimistic "converged").
    assert LoopTrace().exit == EXIT_BUDGET_EXHAUSTED
