import unittest

from deferred_actions.deferred import (
    ContractError,
    CPUOnlyExecutor,
    DeferredAction,
    RECHECK,
    REJECT,
)

NOW = 1000.0


class Clock:
    def __init__(self):
        self.t = NOW

    def __call__(self):
        return self.t


class ContractTests(unittest.TestCase):
    def test_bad_id_rejected(self):
        with self.assertRaises(ContractError):
            DeferredAction("", NOW, 10.0)

    def test_nonpositive_expiry_rejected(self):
        with self.assertRaises(ContractError):
            DeferredAction("a", NOW, 0.0)

    def test_bad_policy_rejected(self):
        with self.assertRaises(ContractError):
            DeferredAction("a", NOW, 10.0, stale_policy="maybe")

    def test_recheck_policy_requires_callable(self):
        with self.assertRaises(ContractError):
            DeferredAction("a", NOW, 10.0, stale_policy=RECHECK, recheck=None)


class StalenessTests(unittest.TestCase):
    def test_expired_action_rejected_before_run(self):
        ran = []
        action = DeferredAction("a1", requested_at=NOW - 100, expires_after_s=10,
                                stale_policy=REJECT, run=lambda: ran.append(1) or 1)
        ex = CPUOnlyExecutor(clock=Clock())
        decision = ex.execute(action, now_ts=NOW)
        self.assertFalse(decision.executed)
        self.assertTrue(decision.stale)
        self.assertIn("expired", decision.reason)
        self.assertEqual(ran, [])
        self.assertEqual(ex.witness_completed(), 0)

    def test_recheck_false_rejects(self):
        action = DeferredAction("a2", requested_at=NOW - 1, expires_after_s=60,
                                stale_policy=RECHECK, recheck=lambda: False,
                                run=lambda: 1)
        ex = CPUOnlyExecutor(clock=Clock())
        decision = ex.execute(action, now_ts=NOW)
        self.assertFalse(decision.executed)
        self.assertTrue(decision.stale)
        self.assertIn("recheck hook", decision.reason)

    def test_recheck_true_executes(self):
        action = DeferredAction("a3", requested_at=NOW - 1, expires_after_s=60,
                                stale_policy=RECHECK, recheck=lambda: True,
                                run=lambda: 42)
        ex = CPUOnlyExecutor(clock=Clock())
        decision = ex.execute(action, now_ts=NOW)
        self.assertTrue(decision.executed)
        self.assertFalse(decision.stale)
        self.assertEqual(decision.result, 42)


class WitnessTests(unittest.TestCase):
    def test_witness_tracks_in_flight_accurately(self):
        ex = CPUOnlyExecutor(clock=Clock())
        seen_in_flight = []

        def probe():
            seen_in_flight.append(ex.witness_in_flight())
            return "ok"

        action = DeferredAction("a4", requested_at=NOW, expires_after_s=60,
                                run=probe)
        decision = ex.execute(action, now_ts=NOW)
        self.assertTrue(decision.executed)
        self.assertEqual(seen_in_flight, [1])
        self.assertEqual(ex.witness_in_flight(), 0)
        self.assertEqual(ex.witness_completed(), 1)

    def test_run_error_is_data_not_crash(self):
        def boom():
            raise RuntimeError("callback fault")
        action = DeferredAction("a5", requested_at=NOW, expires_after_s=60, run=boom)
        ex = CPUOnlyExecutor(clock=Clock())
        decision = ex.execute(action, now_ts=NOW)
        self.assertTrue(decision.executed)
        self.assertIn("RuntimeError", decision.reason)
        self.assertEqual(ex.witness_in_flight(), 0)

    def test_decision_as_dict_opaque_guard(self):
        action = DeferredAction("a6", requested_at=NOW, expires_after_s=60,
                                run=lambda: object())
        ex = CPUOnlyExecutor(clock=Clock())
        d = ex.execute(action, now_ts=NOW).as_dict()
        self.assertEqual(d["result"], "<opaque>")

    def test_staleness_check_never_runs_action(self):
        ran = []
        action = DeferredAction("a7", requested_at=NOW, expires_after_s=60,
                                run=lambda: ran.append(1) or 1)
        ex = CPUOnlyExecutor(clock=Clock())
        stale, reason = ex.staleness_check(action, NOW)
        self.assertFalse(stale)
        self.assertEqual(ran, [])
        self.assertNotIn("a7", ex._in_flight)


if __name__ == "__main__":
    unittest.main()
