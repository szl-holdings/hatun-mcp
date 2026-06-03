"""Quorum math + threshold edge cases for the Byzantine n>=3f+1 quorum (n=5, f=1).

Real logic, no network. Also exercises the BLS aggregate path (real BLS12-381 when
py_ecc is installed; honest Merkle-root fallback otherwise).

SPDX-License-Identifier: Apache-2.0
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hatun_mcp.quorum import QuorumConfig, OrganVote, decide  # noqa: E402
from hatun_mcp.dsse import BlsAggregator, _merkle_root  # noqa: E402


def _votes(verdicts):
    """verdicts: list of (organ, reachable, verdict)."""
    return [OrganVote(organ=o, reachable=r, verdict=v) for o, r, v in verdicts]


def test_config_thresholds_n5_f1():
    c = QuorumConfig(n=5, f=1)
    assert c.tolerates_byzantine() is True          # 5 >= 3*1+1
    assert c.min_total() == 4                        # 3f+1
    assert c.agreement_threshold() == 3              # 2f+1


def test_config_too_small_is_not_byzantine_safe():
    assert QuorumConfig(n=3, f=1).tolerates_byzantine() is False  # 3 < 4
    assert QuorumConfig(n=2, f=1).tolerates_byzantine() is False


def test_unanimous_five_reaches_quorum():
    res = decide(_votes([("a11oy", True, "ALLOW"), ("amaru", True, "ALLOW"),
                         ("sentra", True, "ALLOW"), ("killinchu", True, "ALLOW"),
                         ("rosie", True, "ALLOW")]))
    assert res.outcome == "QUORUM_REACHED"
    assert res.decided_verdict == "ALLOW"
    assert res.reachable == 5


def test_a11oy_down_four_live_still_reaches_quorum():
    # a11oy paused (the real 2026-06-03 state): 4 reachable, 4 agree.
    res = decide(_votes([("a11oy", False, None), ("amaru", True, "DENY"),
                         ("sentra", True, "DENY"), ("killinchu", True, "DENY"),
                         ("rosie", True, "DENY")]))
    assert res.outcome == "QUORUM_REACHED"
    assert res.decided_verdict == "DENY"
    assert res.reachable == 4
    assert res.to_dict()["byzantine_safe"] is True


def test_three_reachable_is_no_quorum():
    # Only 3 reachable < 3f+1 = 4 -> NO_QUORUM even if they all agree.
    res = decide(_votes([("a11oy", False, None), ("amaru", False, None),
                         ("sentra", True, "ALLOW"), ("killinchu", True, "ALLOW"),
                         ("rosie", True, "ALLOW")]))
    assert res.outcome == "NO_QUORUM"
    assert res.decided_verdict is None


def test_split_vote_no_decision():
    # 4 reachable but split 2/2 -> no 2f+1 majority -> SPLIT.
    res = decide(_votes([("a11oy", True, "ALLOW"), ("amaru", True, "ALLOW"),
                         ("sentra", True, "DENY"), ("killinchu", True, "DENY"),
                         ("rosie", False, None)]))
    assert res.outcome == "SPLIT"
    assert res.decided_verdict is None


def test_exact_threshold_three_of_four():
    # 4 reachable, 3 ALLOW / 1 DENY -> 3 >= 2f+1 -> QUORUM_REACHED ALLOW.
    res = decide(_votes([("a11oy", True, "ALLOW"), ("amaru", True, "ALLOW"),
                         ("sentra", True, "ALLOW"), ("killinchu", True, "DENY"),
                         ("rosie", False, None)]))
    assert res.outcome == "QUORUM_REACHED"
    assert res.decided_verdict == "ALLOW"


def test_dict_verdicts_tally_canonically():
    v = [("a", True, {"x": 1}), ("b", True, {"x": 1}), ("c", True, {"x": 1}),
         ("d", True, {"x": 2})]
    res = decide(_votes(v))
    assert res.outcome == "QUORUM_REACHED"
    assert res.decided_verdict == {"x": 1}


def test_merkle_root_deterministic():
    h = ["a" * 64, "b" * 64, "c" * 64]
    assert _merkle_root(h) == _merkle_root(h)
    assert _merkle_root([]) == "0" * 64
    assert _merkle_root(["a" * 64]) != _merkle_root(["b" * 64])


def test_bls_aggregate_and_verify():
    agg = BlsAggregator(seed="test-seed")
    receipts = [("a11oy", "11" * 32), ("amaru", "22" * 32), ("sentra", "33" * 32)]
    out = agg.aggregate(receipts)
    assert out.n_organs == 3
    assert out.mode in ("BLS12-381", "MERKLE-AGG")
    assert out.merkle_root == _merkle_root([h for _, h in receipts])
    # round-trip verify in whichever mode is active
    assert agg.verify(receipts, out.aggregate) is True
    if out.mode == "BLS12-381":
        # tampering one receipt must fail BLS AggregateVerify
        bad = [("a11oy", "11" * 32), ("amaru", "22" * 32), ("sentra", "44" * 32)]
        assert agg.verify(bad, out.aggregate) is False


def test_empty_aggregate_is_genesis_merkle():
    out = BlsAggregator().aggregate([])
    assert out.n_organs == 0
    assert out.merkle_root == "0" * 64
