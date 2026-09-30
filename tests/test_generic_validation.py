"""Synthetic contracts for selected generic functions; no server import or keys.

The AST loader executes named definitions from actual source, excluding module
startup, provider imports, operational tools, signing and adapter registration.
This is unit evidence, not a full-server or transport integration test.
Run: python -m unittest discover -s tests -p test_generic_validation.py -v
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Awaitable, Callable, Optional
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def selected_source(filename, names, values):
    path = SOURCE_ROOT / "hatun_mcp" / filename
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    definitions = [node for node in tree.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                   and node.name in names]
    # The helper is absent at the audit baseline; loading that revision must
    # reproduce behavioral failures, not fail merely because a helper was added.
    assert set(names) - {"_backend_succeeded", "observed_signer_mode"} <= {node.name for node in definitions}
    assert all(not node.decorator_list or node.decorator_list == []
               or isinstance(node, ast.ClassDef) for node in definitions)
    module = ModuleType("_hatun_synthetic_" + path.stem)
    module.__dict__.update(values)
    sys.modules[module.__name__] = module
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    projection = ast.fix_missing_locations(ast.Module(body=[future, *definitions], type_ignores=[]))
    exec(compile(projection, str(path), "exec"), module.__dict__)
    return module


def immediate(coro):
    """Drive only fixture coroutines that never suspend on I/O or a scheduler."""
    try:
        coro.send(None)
    except StopIteration as done:
        return done.value
    else:
        raise AssertionError("fixture unexpectedly suspended")
    finally:
        coro.close()


class GenericValidationTests(unittest.TestCase):
    def state(self, signer, verification=True):
        module = selected_source("state.py", (
            "_iso", "_first_line", "_observed_revision", "_tool_family",
            "_tool_rows", "_resource_rows", "_parity", "_organ_registration", "console_state", "observed_signer_mode",
        ), dict(
            Any=Any, os=SimpleNamespace(environ={}), datetime=datetime, timezone=timezone,
            time=SimpleNamespace(time=lambda: 1, monotonic=lambda: 1),
            platform=SimpleNamespace(python_version=lambda: "synthetic"),
            UNAVAILABLE="UNAVAILABLE", STRUCTURAL_ONLY="STRUCTURAL-ONLY",
            _PROCESS_START_WALL=0, _PROCESS_START_MONOTONIC=0, card_tool_names=lambda: [],
        ))
        doctrine = dict(protocol_revision="synthetic", lean_declarations=0,
                        lean_axioms_unique=0, lean_sorries_total=0, yuyay_axes=0,
                        slsa="synthetic", lean_measured_sha="synthetic")
        chain = SimpleNamespace(verify=lambda: verification, depth=lambda: 0, head_hash=lambda: "synthetic")
        mcp = SimpleNamespace(
            _tool_manager=SimpleNamespace(list_tools=lambda: []),
            _resource_manager=SimpleNamespace(list_resources=lambda: []),
        )
        return module.console_state(mcp=mcp, khipu=chain, signer=signer, doctrine=doctrine)

    def backend(self, result=None, *, raises=False, evidence=False, authenticated=True):
        receipts, recorded = [], []

        def emit(**kwargs):
            receipts.append(kwargs)
            return kwargs

        context = lambda value: SimpleNamespace(get=lambda: value)
        module = selected_source("server.py", ("_scope_ok", "_backend_succeeded", "governed", "_summ"), dict(
            Any=Any, Optional=Optional, time=SimpleNamespace(time=lambda: 1),
            DEFAULT_LATENCY_BUDGET=1, ALLOW_ANON=False,
            _ctx_client=context("synthetic-client" if authenticated else None),
            _ctx_scope=context("read"), _ctx_sovereign=context(False), _ctx_second_approver=context(None),
            CLIENTS=SimpleNamespace(reputation=lambda _: 1, record=lambda _, **kw: recorded.append(kw)),
            KHIPU=SimpleNamespace(verify=lambda: True, emit=emit), SIGNER=object(),
            yuyay_gate=lambda _: SimpleNamespace(passed=True, min_axis_value=1, scores={}),
            hatun_mcp_factor=lambda **_: 1, puriq_utility=lambda **_: 1,
            hukla_check=lambda **_: None, _wrap=lambda **kw: kw,
            B=SimpleNamespace(GITHUB_ESTATE_SCHEMA="synthetic/v1", _github_canonical_digest=lambda _: "digest"),
        ))
        called = []

        async def echo():
            called.append(True)
            if raises:
                raise ValueError("synthetic-private-marker")
            return result

        response = immediate(module.governed(tool="audit_echo", operation_id="synthetic.echo",
                                            gate_text="benign echo", backend_coro=echo(),
                                            evidence_contract=evidence))
        return response, receipts, recorded, called

    def loop(self, step, converged=None, *, budget=2):
        module = selected_source("loop.py", ("loop_max_steps", "LoopStep", "LoopTrace", "run_bounded_loop"), dict(
            Any=Any, Optional=Optional, Callable=Callable, Awaitable=Awaitable,
            dataclass=dataclass, field=field, os=SimpleNamespace(environ={}),
            DEFAULT_MAX_STEPS=12, _ENV_MAX_STEPS="SYNTHETIC", DOCTRINE_LINE="synthetic",
            EXIT_CONVERGED="converged", EXIT_BUDGET_EXHAUSTED="budget_exhausted", EXIT_ERROR="error",
        ))
        return immediate(module.run_bounded_loop(["a", "b"], step, max_steps=budget, converged=converged))

    def test_unknown_and_malformed_modes_never_ready(self):
        for mode in (None, "", "unknown", "PLACEHOLDER", 1, True, {}, []):
            with self.subTest(mode=mode):
                out = self.state(SimpleNamespace(mode=mode))
                self.assertEqual(out["health"]["readiness"], "NOT-READY")
                self.assertEqual(out["signing"]["state"], "UNSIGNED")
        self.assertEqual(self.state(object())["health"]["readiness"], "NOT-READY")

    def test_unreadable_mode_is_unavailable(self):
        class Broken:
            @property
            def mode(self):
                raise ValueError("synthetic-private-marker")
        out = self.state(Broken())
        self.assertEqual(out["signing"]["signer_mode"], "UNAVAILABLE")
        self.assertNotIn("synthetic-private-marker", str(out))

    def test_chain_requires_literal_true(self):
        for value in (False, None, 1, "false", [True], {}):
            with self.subTest(value=value):
                out = self.state(SimpleNamespace(mode="ECDSA-P256"), value)
                self.assertEqual(out["health"]["readiness"], "NOT-READY")
                self.assertEqual(out["khipu"]["chain"], "FAILED")

    def test_recognized_mode_and_verified_chain_remain_ready(self):
        out = self.state(SimpleNamespace(mode="ECDSA-P256"))
        self.assertEqual(out["health"]["readiness"], "READY")
        self.assertEqual(out["signing"]["state"], "SIGNED")

    def readyz(self, signer, verification=True, *, broken_chain=False):
        helper = selected_source("state.py", ("observed_signer_mode",), dict(Any=Any, UNAVAILABLE="UNAVAILABLE"))
        def verify():
            if broken_chain:
                raise ValueError("synthetic-private-marker")
            return verification
        values = dict(SIGNER=signer, KHIPU=SimpleNamespace(verify=verify),
                      DOCTRINE=dict(protocol_revision="synthetic"),
                      JSONResponse=lambda content, **kw: dict(content=content, **kw))
        if hasattr(helper, "observed_signer_mode"):
            values["observed_signer_mode"] = helper.observed_signer_mode
        module = selected_source("server_http.py", ("readyz",), values)
        return immediate(module.readyz(None))

    def test_http_readiness_unknown_modes_are_503(self):
        for signer in (object(), SimpleNamespace(mode=None), SimpleNamespace(mode="unknown"),
                       SimpleNamespace(mode="PLACEHOLDER"), SimpleNamespace(mode={})):
            with self.subTest(signer=signer):
                response = self.readyz(signer)
                self.assertEqual(response["status_code"], 503)
                self.assertIs(response["content"]["ready"], False)

    def test_http_readiness_chain_verification_is_strict(self):
        for value in (False, None, 1, "false", [True]):
            with self.subTest(value=value):
                response = self.readyz(SimpleNamespace(mode="ECDSA-P256"), value)
                self.assertEqual(response["status_code"], 503)
                self.assertIs(response["content"]["ready"], False)

    def test_http_readiness_handles_unreadable_dependencies(self):
        response = self.readyz(SimpleNamespace(mode="ECDSA-P256"), broken_chain=True)
        self.assertEqual(response["status_code"], 503)
        self.assertEqual(response["content"]["checks"]["receipt_chain"], "UNAVAILABLE")
        self.assertNotIn("synthetic-private-marker", str(response))
        class BrokenSigner:
            @property
            def mode(self):
                raise ValueError("synthetic-private-marker")
        response = self.readyz(BrokenSigner())
        self.assertEqual(response["status_code"], 503)
        self.assertEqual(response["content"]["signer_mode"], "UNAVAILABLE")
        self.assertNotIn("synthetic-private-marker", str(response))

    def test_http_readiness_recognized_mode_preserves_success(self):
        response = self.readyz(SimpleNamespace(mode="ECDSA-P256"))
        self.assertEqual(response["status_code"], 200)
        self.assertIs(response["content"]["ready"], True)
        self.assertEqual(response["headers"], {"Cache-Control": "no-store"})

    def test_backend_errors_never_emit_success_receipts(self):
        for error in ("http_500", "", False, 0, [], {}):
            for deployed in (True, False, None):
                with self.subTest(error=error, deployed=deployed):
                    # Error must dominate even an otherwise successful HTTP status.
                    out, receipts, recorded, _ = self.backend(dict(deployed=deployed, error=error, http_status=200))
                    self.assertEqual(out["status"], "failure")
                    self.assertEqual(receipts[0]["status"], "failure")
                    self.assertFalse(recorded[0]["clean"])

    def test_malformed_or_missing_results_never_succeed(self):
        for result in (None, [], "synthetic", True, 1, {}, {"error": None},
                       {"deployed": "true"}, {"deployed": 1}, {"deployed": False}):
            with self.subTest(result=result):
                out, receipts, _, _ = self.backend(result)
                self.assertEqual(out["status"], "failure")
                self.assertEqual(receipts[0]["status"], "failure")

    def test_invalid_http_status_never_succeeds(self):
        for status in (True, "200", 0, 199, 400, 500, [], float("nan")):
            with self.subTest(status=status):
                out, _, _, _ = self.backend(dict(deployed=True, error=None, http_status=status))
                self.assertEqual(out["status"], "failure")

    def test_valid_local_and_http_results_remain_successful(self):
        for status in (None, 200, 204, 299, 302):
            with self.subTest(status=status):
                out, receipts, recorded, called = self.backend(dict(deployed=True, error=None, http_status=status))
                self.assertEqual(out["status"], "success")
                self.assertEqual(receipts[0]["status"], "success")
                self.assertTrue(recorded[0]["clean"])
                self.assertEqual(called, [True])

    def test_backend_exception_is_sanitized_failure(self):
        out, receipts, _, _ = self.backend(raises=True)
        self.assertEqual(out["status"], "failure")
        self.assertEqual(receipts[0]["detail"]["backend_error"], "BACKEND_RESULT_ERROR")
        self.assertNotIn("synthetic-private-marker", str((out, receipts)))

    def test_declined_read_does_not_execute_callback(self):
        out, receipts, _, called = self.backend(authenticated=False)
        self.assertEqual(out["status"], "declined")
        self.assertEqual(receipts[0]["status"], "declined")
        self.assertEqual(called, [])

    def test_evidence_contract_retains_stricter_classification(self):
        for state in ("COMPLETE", "INCOMPLETE", "UNAVAILABLE"):
            with self.subTest(state=state):
                result = dict(data=dict(schema="synthetic/v1", state=state, evidence=dict(digest="digest")),
                              evidence_digest_sha256="digest", evidence_schema="synthetic/v1",
                              evidence_state=state, error=None if state == "COMPLETE" else "unavailable")
                out, receipts, _, _ = self.backend(result, evidence=True)
                expected = "success" if state == "COMPLETE" else "failure"
                self.assertEqual(out["status"], expected)
                self.assertEqual(receipts[0]["status"], expected)
        out, receipts, _, _ = self.backend({}, evidence=True)
        self.assertEqual(out["status"], "failure")
        self.assertEqual(receipts[0]["detail"]["backend_error"], "EVIDENCE_CONTRACT_ERROR")

    def test_step_exception_is_sanitized_terminal_error(self):
        async def step(*_):
            raise ValueError("synthetic-private-marker")
        result, trace = self.loop(step)
        self.assertEqual(result, [])
        self.assertEqual(trace.exit, "error")
        self.assertEqual(trace.trace[-1].label, "step 0: step_error")
        self.assertNotIn("synthetic-private-marker", str(trace.to_dict()))

    def test_predicate_exception_is_sanitized_terminal_error(self):
        async def step(_, item, __):
            return item
        def predicate(_):
            raise ValueError("synthetic-private-marker")
        result, trace = self.loop(step, predicate)
        self.assertEqual(result, ["a"])
        self.assertEqual(trace.exit, "error")
        self.assertEqual(trace.trace[-1].label, "step 0: convergence_error")
        self.assertNotIn("synthetic-private-marker", str(trace.to_dict()))

    def test_malformed_predicate_results_are_errors(self):
        async def step(_, item, __):
            return item
        for value in (None, 1, "false", [], {}):
            with self.subTest(value=value):
                result, trace = self.loop(step, lambda _: value)
                self.assertEqual(trace.exit, "error")
                self.assertEqual(result, ["a"])

    def test_valid_predicates_and_budget_keep_existing_semantics(self):
        async def step(_, item, __):
            return item
        result, trace = self.loop(step, lambda _: True)
        self.assertEqual((result, trace.exit), (["a"], "converged"))
        result, trace = self.loop(step, lambda _: False)
        self.assertEqual((result, trace.exit), (["a", "b"], "converged"))
        result, trace = self.loop(step, budget=1)
        self.assertEqual((result, trace.exit), (["a"], "budget_exhausted"))


if __name__ == "__main__":
    unittest.main()
