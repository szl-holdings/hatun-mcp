#!/usr/bin/env python3
"""Regression tests for the formula-evaluator math defects (Phase A H1-H5)."""
import math, sys, unittest
sys.path.insert(0, ".")
from hatun_mcp import formulas as F


class TestPinsker(unittest.TestCase):
    def test_disjoint_distributions_infinite_kl(self):
        # H1: P=[1,0], Q=[0,1] previously returned bound 0.0 (true TV=1)
        r = F.pinsker_kl_bound({"p": [1, 0], "q": [0, 1]})
        self.assertEqual(r["kl"], "Infinity")
        self.assertEqual(r["value"], "Infinity")

    def test_unnormalized_rejected(self):
        # H2: unnormalized vectors were silently accepted
        with self.assertRaises(ValueError):
            F.pinsker_kl_bound({"p": [2, 2], "q": [1, 1]})

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            F.pinsker_kl_bound({"p": [], "q": []})

    def test_identical_distributions_zero(self):
        r = F.pinsker_kl_bound({"p": [0.5, 0.5], "q": [0.5, 0.5]})
        self.assertEqual(r["kl"], 0.0)
        self.assertEqual(r["value"], 0.0)

    def test_valid_bound_holds(self):
        p, q = [0.9, 0.1], [0.5, 0.5]
        r = F.pinsker_kl_bound({"p": p, "q": q})
        tv = 0.5 * sum(abs(a - b) for a, b in zip(p, q))
        self.assertLessEqual(tv, r["value"] + 1e-12)


class TestFisherRao(unittest.TestCase):
    def test_empty_rejected(self):
        # H3: empty lists previously raised ZeroDivisionError deep inside
        with self.assertRaises(ValueError):
            F.fisher_rao_distance({"p": [], "q": []})

    def test_valid_distance(self):
        r = F.fisher_rao_distance({"p": [1.0], "q": [1.0]})
        self.assertEqual(r["value"], 0.0)


class TestReidemeister(unittest.TestCase):
    def test_r1_applies(self):
        r = F.reidemeister_invariant({"braid_word": "aA", "move": "R1"})
        self.assertEqual(r["output"], "")

    def test_r2_r3_unsupported(self):
        # H4: the move parameter was previously validated then ignored
        for move in ("R2", "R3"):
            with self.assertRaises(ValueError):
                F.reidemeister_invariant({"braid_word": "aA", "move": move})


class TestDSSE(unittest.TestCase):
    def test_standard_pae_vector(self):
        # H5: standard DSSEv1 PAE with decimal lengths and payloadType binding
        r = F.dsse_envelope({"payload": "hello", "payload_type": "application/json"})
        import hashlib
        expected_pae = (b"DSSEv1 " + b"16" + b" " + b"application/json"
                        + b" " + b"5" + b" " + b"hello")
        self.assertEqual(r["value"], hashlib.sha256(expected_pae).hexdigest())
        self.assertFalse(r["signed"])

    def test_payload_type_bound(self):
        a = F.dsse_envelope({"payload": "x", "payload_type": "a"})
        b = F.dsse_envelope({"payload": "x", "payload_type": "b"})
        self.assertNotEqual(a["value"], b["value"])


if __name__ == "__main__":
    unittest.main()


class TestPinskerSubnormal(unittest.TestCase):
    def test_subnormal_q_finite_kl(self):
        # pi normal over qi subnormal previously overflowed the ratio to inf
        tiny = 5e-324
        r = F.pinsker_kl_bound({"p": [0.5, 0.5], "q": [1.0 - tiny, tiny]})
        self.assertIsInstance(r["kl"], float)
        self.assertTrue(math.isfinite(r["kl"]))
        self.assertTrue(math.isfinite(r["value"]))
        # true KL = 0.5*ln(0.5/tiny) + 0.5*ln(0.5/(1-tiny)) ~ 371.9
        self.assertGreater(r["kl"], 300.0)

    def test_result_always_strict_json(self):
        import json
        for args in ({"p": [1, 0], "q": [0, 1]},
                     {"p": [0.5, 0.5], "q": [1.0 - 5e-324, 5e-324]},
                     {"p": [0.9, 0.1], "q": [0.5, 0.5]}):
            r = F.pinsker_kl_bound(args)
            json.dumps(r, allow_nan=False)  # must never raise
