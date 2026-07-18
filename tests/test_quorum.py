"""Quorum math + threshold edge cases for the Byzantine n>=3f+1 quorum (n=5, f=1).

Real logic, no network. Also exercises the BLS aggregate path (real BLS12-381 when
py_ecc is installed; honest Merkle-root fallback otherwise).

SPDX-License-Identifier: Apache-2.0
"""
import json
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
    assert QuorumConfig(n=3, f=1).is_valid() is False


def test_config_is_valid_rejects_ill_formed():
    # Well-formed Byzantine configs are valid.
    assert QuorumConfig(n=5, f=1).is_valid() is True
    assert QuorumConfig(n=1, f=0, participants=("solo",)).is_valid() is True
    # A negative fault budget drives 2f+1 <= 0 -> fail-open -> must be rejected.
    assert QuorumConfig(n=5, f=-1).is_valid() is False
    assert QuorumConfig(n=5, f=-2).is_valid() is False
    # Zero / negative participant count is ill-formed.
    assert QuorumConfig(n=0, f=0).is_valid() is False
    assert QuorumConfig(n=-3, f=0).is_valid() is False


def test_negative_f_config_fails_closed_not_open():
    """Regression: a negative f makes 2f+1 <= 0. Without the fail-closed guard a
    SINGLE vote would forge QUORUM_REACHED. decide() must refuse and return
    NO_QUORUM — Byzantine safety is never fabricated from an unsafe config."""
    one_vote = _votes([("a11oy", True, "ALLOW")])
    res = decide(one_vote, QuorumConfig(n=5, f=-1))
    assert res.outcome == "NO_QUORUM"
    assert res.decided_verdict is None
    assert "ill-formed" in res.reason
    # Even a would-be unanimous set cannot forge quorum under an ill-formed config.
    unanimous = _votes([("a11oy", True, "ALLOW"), ("llm", True, "ALLOW"),
                        ("immune", True, "ALLOW"), ("killinchu", True, "ALLOW"),
                        ("companion", True, "ALLOW")])
    res2 = decide(unanimous, QuorumConfig(n=5, f=-1))
    assert res2.outcome == "NO_QUORUM"
    assert res2.decided_verdict is None


def test_empty_votes_ill_formed_config_fails_closed():
    # No votes + negative f: threshold is <= 0, but decide must NOT declare quorum.
    res = decide([], QuorumConfig(n=5, f=-1))
    assert res.outcome == "NO_QUORUM"
    assert res.decided_verdict is None


def test_unsafe_n_f_config_fails_closed_even_with_enough_submitted_votes():
    votes = _votes([("a", True, "ALLOW"), ("b", True, "ALLOW"),
                    ("c", True, "ALLOW"), ("d", True, "ALLOW")])
    res = decide(votes, QuorumConfig(n=3, f=1))
    assert res.outcome == "NO_QUORUM"
    assert res.decided_verdict is None
    assert res.to_dict()["byzantine_safe"] is False


def test_unanimous_five_reaches_quorum():
    res = decide(_votes([("a11oy", True, "ALLOW"), ("llm", True, "ALLOW"),
                         ("immune", True, "ALLOW"), ("killinchu", True, "ALLOW"),
                         ("companion", True, "ALLOW")]))
    assert res.outcome == "QUORUM_REACHED"
    assert res.decided_verdict == "ALLOW"
    assert res.reachable == 5


def test_a11oy_down_four_live_still_reaches_quorum():
    # a11oy paused (the real 2026-06-03 state): 4 reachable, 4 agree.
    res = decide(_votes([("a11oy", False, None), ("llm", True, "DENY"),
                         ("immune", True, "DENY"), ("killinchu", True, "DENY"),
                         ("companion", True, "DENY")]))
    assert res.outcome == "QUORUM_REACHED"
    assert res.decided_verdict == "DENY"
    assert res.reachable == 4
    assert res.to_dict()["byzantine_safe"] is True


def test_three_reachable_is_no_quorum():
    # Only 3 reachable < 3f+1 = 4 -> NO_QUORUM even if they all agree.
    res = decide(_votes([("a11oy", False, None), ("llm", False, None),
                         ("immune", True, "ALLOW"), ("killinchu", True, "ALLOW"),
                         ("companion", True, "ALLOW")]))
    assert res.outcome == "NO_QUORUM"
    assert res.decided_verdict is None


def test_split_vote_no_decision():
    # 4 reachable but split 2/2 -> no 2f+1 majority -> SPLIT.
    res = decide(_votes([("a11oy", True, "ALLOW"), ("llm", True, "ALLOW"),
                         ("immune", True, "DENY"), ("killinchu", True, "DENY"),
                         ("companion", False, None)]))
    assert res.outcome == "SPLIT"
    assert res.decided_verdict is None


def test_exact_threshold_three_of_four():
    # 4 reachable, 3 ALLOW / 1 DENY -> 3 >= 2f+1 -> QUORUM_REACHED ALLOW.
    res = decide(_votes([("a11oy", True, "ALLOW"), ("llm", True, "ALLOW"),
                         ("immune", True, "ALLOW"), ("killinchu", True, "DENY"),
                         ("companion", False, None)]))
    assert res.outcome == "QUORUM_REACHED"
    assert res.decided_verdict == "ALLOW"


def test_dict_verdicts_tally_canonically():
    v = [("a11oy", True, {"x": 1}), ("llm", True, {"x": 1}),
         ("immune", True, {"x": 1}), ("killinchu", True, {"x": 2})]
    res = decide(_votes(v))
    assert res.outcome == "QUORUM_REACHED"
    assert res.decided_verdict == {"x": 1}


def test_duplicate_organ_cannot_forge_quorum():
    votes = _votes([("a11oy", True, "ALLOW"), ("a11oy", True, "ALLOW"),
                    ("a11oy", True, "ALLOW"), ("immune", True, "DENY")])
    res = decide(votes)
    assert res.outcome == "NO_QUORUM"
    assert res.decided_verdict is None
    assert "duplicate organ identity" in res.reason
    assert res.to_dict()["byzantine_safe"] is False


def test_duplicate_organ_case_variant_cannot_forge_quorum():
    votes = _votes([("A11OY", True, "ALLOW"), ("a11oy", True, "ALLOW"),
                    ("immune", True, "ALLOW"), ("llm", True, "ALLOW")])
    res = decide(votes)
    assert res.outcome == "NO_QUORUM"
    assert "duplicate organ identity" in res.reason


def test_more_votes_than_configured_participants_fails_closed():
    votes = _votes([("a", True, "ALLOW"), ("b", True, "ALLOW"),
                    ("c", True, "ALLOW"), ("d", True, "ALLOW"),
                    ("e", True, "ALLOW"), ("f", True, "ALLOW")])
    res = decide(votes, QuorumConfig(n=5, f=1))
    assert res.outcome == "NO_QUORUM"
    assert "configured n=5" in res.reason


def test_verdict_types_do_not_collide():
    votes = _votes([("a11oy", True, True), ("llm", True, "True"),
                    ("immune", True, True), ("killinchu", True, "True")])
    res = decide(votes)
    assert res.outcome == "SPLIT"
    assert res.decided_verdict is None


def test_non_finite_and_unsupported_verdicts_fail_closed():
    nan_votes = _votes([("a11oy", True, float("nan")), ("llm", True, "ALLOW"),
                        ("immune", True, "ALLOW"), ("killinchu", True, "ALLOW")])
    nan_result = decide(nan_votes)
    assert nan_result.outcome == "NO_QUORUM"
    assert "non-finite float" in nan_result.reason
    assert nan_result.to_dict()["byzantine_safe"] is False
    json.dumps(nan_result.to_dict(), allow_nan=False)

    object_votes = _votes([("a11oy", True, object()), ("llm", True, "ALLOW"),
                           ("immune", True, "ALLOW"), ("killinchu", True, "ALLOW")])
    object_result = decide(object_votes)
    assert object_result.outcome == "NO_QUORUM"
    assert "unsupported type object" in object_result.reason
    json.dumps(object_result.to_dict(), allow_nan=False)


def test_nested_python_json_coercions_cannot_forge_quorum():
    votes = _votes([
        ("a11oy", True, {"1": "ALLOW"}),
        ("llm", True, {1: "ALLOW"}),
        ("immune", True, {"1": "ALLOW"}),
        ("killinchu", True, "DENY"),
    ])
    result = decide(votes)
    assert result.outcome == "NO_QUORUM"
    assert "non-string object key" in result.reason
    assert result.to_dict()["byzantine_safe"] is False

    tuple_result = decide(_votes([
        ("a11oy", True, ["ALLOW", (1, 2)]),
        ("llm", True, ["ALLOW", [1, 2]]),
        ("immune", True, ["ALLOW", [1, 2]]),
        ("killinchu", True, "DENY"),
    ]))
    assert tuple_result.outcome == "NO_QUORUM"
    assert "unsupported type tuple" in tuple_result.reason


def test_malformed_configs_are_total_json_safe_and_never_safe():
    configs = [
        QuorumConfig(n="5", f=1),
        QuorumConfig(n=True, f=1),
        QuorumConfig(n=5.0, f=1),
        QuorumConfig(n=5, f=-1),
        QuorumConfig(n=5, f=False),
        QuorumConfig(n=5, f=1, participants=object()),
        QuorumConfig(n=10**5000, f=1),
        QuorumConfig(n=5, f=10**5000),
    ]
    for config in configs:
        result = decide([], config)
        assert result.outcome == "NO_QUORUM"
        assert result.to_dict()["byzantine_safe"] is False
        json.dumps(result.to_dict(), allow_nan=False)


def test_huge_integer_verdict_fails_closed_and_remains_json_safe():
    result = decide(_votes([
        ("a11oy", True, 10**5000),
        ("llm", True, "ALLOW"),
        ("immune", True, "ALLOW"),
        ("killinchu", True, "ALLOW"),
    ]))
    assert result.outcome == "NO_QUORUM"
    assert "signed 64-bit" in result.reason
    assert result.to_dict()["byzantine_safe"] is False
    json.dumps(result.to_dict(), allow_nan=False)


def test_vote_metadata_and_container_shape_fail_closed_json_safe():
    bad_votes = [
        OrganVote(organ=object(), reachable=True, verdict="ALLOW", receipt_hash=object()),
        OrganVote(organ="llm", reachable=1, verdict="ALLOW", receipt_hash=None),
        OrganVote(organ="immune", reachable=True, verdict="ALLOW", receipt_hash=object()),
    ]
    for vote in bad_votes:
        result = decide([vote])
        assert result.outcome == "NO_QUORUM"
        assert result.to_dict()["byzantine_safe"] is False
        json.dumps(result.to_dict(), allow_nan=False)

    raw_result = decide([object()])
    assert raw_result.outcome == "NO_QUORUM"
    json.dumps(raw_result.to_dict(), allow_nan=False)

    tuple_result = decide(tuple())  # type: ignore[arg-type]
    assert tuple_result.outcome == "NO_QUORUM"
    json.dumps(tuple_result.to_dict(), allow_nan=False)


def test_participants_are_registry_bound_and_unicode_canonical():
    sybil = decide(_votes([("attacker-1", True, "ALLOW")]))
    assert sybil.outcome == "NO_QUORUM"
    assert "outside the configured participant registry" in sybil.reason

    noncanonical = QuorumConfig(n=1, f=0, participants=("Å",))
    result = decide([], noncanonical)
    assert result.outcome == "NO_QUORUM"
    assert "NFKC-normalized" in result.reason


def test_cyclic_and_overdeep_verdicts_fail_closed_without_crashing():
    cyclic = []
    cyclic.append(cyclic)
    cyclic_result = decide(_votes([
        ("a11oy", True, cyclic),
        ("llm", True, "ALLOW"),
        ("immune", True, "ALLOW"),
        ("killinchu", True, "ALLOW"),
    ]))
    assert cyclic_result.outcome == "NO_QUORUM"
    assert "cyclic list" in cyclic_result.reason
    json.dumps(cyclic_result.to_dict(), allow_nan=False)

    deep = "ALLOW"
    for _ in range(34):
        deep = [deep]
    deep_result = decide(_votes([
        ("a11oy", True, deep),
        ("llm", True, "ALLOW"),
        ("immune", True, "ALLOW"),
        ("killinchu", True, "ALLOW"),
    ]))
    assert deep_result.outcome == "NO_QUORUM"
    assert "depth limit" in deep_result.reason
    json.dumps(deep_result.to_dict(), allow_nan=False)


def test_merkle_root_deterministic():
    h = ["a" * 64, "b" * 64, "c" * 64]
    assert _merkle_root(h) == _merkle_root(h)
    assert _merkle_root([]) == "0" * 64
    assert _merkle_root(["a" * 64]) != _merkle_root(["b" * 64])


def test_bls_aggregate_and_verify():
    agg = BlsAggregator(seed="test-seed")
    receipts = [("a11oy", "11" * 32), ("llm", "22" * 32), ("immune", "33" * 32)]
    out = agg.aggregate(receipts)
    assert out.n_organs == 3
    assert out.mode in ("BLS12-381", "MERKLE-AGG")
    assert out.merkle_root == _merkle_root([h for _, h in receipts])
    # round-trip verify in whichever mode is active
    assert agg.verify(receipts, out.aggregate) is True
    if out.mode == "BLS12-381":
        # tampering one receipt must fail BLS AggregateVerify
        bad = [("a11oy", "11" * 32), ("llm", "22" * 32), ("immune", "44" * 32)]
        assert agg.verify(bad, out.aggregate) is False


def test_empty_aggregate_is_genesis_merkle():
    out = BlsAggregator().aggregate([])
    assert out.n_organs == 0
    assert out.merkle_root == "0" * 64
