"""
hatun_mcp.quorum — Byzantine fault-tolerant quorum for governance-critical tools.

Governance-critical MCP tools (Λ verdicts: szl_puriq_evaluate, a11oy/immune/
companion policy verdicts) must NOT trust a single organ. We require a Byzantine
quorum across the five SZL organs.

Model (classic BFT, e.g. PBFT):
  * n participating organs, tolerate f Byzantine (arbitrary-fault) participants.
  * SAFETY requires      n >= 3f + 1.
  * AGREEMENT requires   >= 2f + 1 matching verdicts (a quorum that necessarily
    intersects any other quorum in at least one honest node).

Default config: n = 5 organs (a11oy, llm, immune, killinchu, companion), f = 1.
  -> min_total() = 3f+1 = 4 reachable organs required.
  -> agreement_threshold() = 2f+1 = 3 matching verdicts required.

HONEST DEGRADATION: if only 4 of 5 organs are reachable, n=4,f=1 still satisfies
n>=3f+1 (4>=4), and 2f+1 = 3 matching verdicts still reaches quorum on the 4 live
organs. If a second organ drops (n=3 < 4) the quorum returns NO_QUORUM — disclosed,
never forced.

SPDX-License-Identifier: Apache-2.0
Author: Yachay (CTO authority) · Built by Perplexity Computer Agent · 2026-06-03
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

ORGANS = ("a11oy", "llm", "immune", "killinchu", "companion")


@dataclass(frozen=True)
class QuorumConfig:
    n: int = 5
    f: int = 1

    def tolerates_byzantine(self) -> bool:
        """True iff the configured n can tolerate f Byzantine faults (n >= 3f+1)."""
        return self.n >= 3 * self.f + 1

    def min_total(self) -> int:
        """Minimum number of reachable participants for a valid quorum: 3f+1."""
        return 3 * self.f + 1

    def agreement_threshold(self) -> int:
        """Matching-verdict count required to decide: 2f+1."""
        return 2 * self.f + 1

    def is_valid(self) -> bool:
        """True iff this is a well-formed Byzantine config that decide() may act on.

        Requires a NON-NEGATIVE fault budget f and at least one participant, which
        gives strictly positive agreement (2f+1) and safety (3f+1) thresholds. A
        negative f is rejected FAIL-CLOSED: it drives 2f+1 <= 0, and any threshold
        <= 0 is trivially satisfied by a single (or even zero) matching vote — a
        fail-open hole that would let one organ forge quorum. Byzantine safety is
        never fabricated: an ill-formed config must not decide.
        """
        return (
            self.f >= 0
            and self.n >= 1
            and self.agreement_threshold() >= 1
            and self.min_total() >= 1
        )


@dataclass
class OrganVote:
    organ: str
    reachable: bool
    verdict: Optional[Any]              # the organ's verdict (e.g. "ALLOW"/"DENY"); None if unreachable
    receipt_hash: Optional[str] = None  # Khipu receipt hash for this organ's contribution
    detail: dict = field(default_factory=dict)


@dataclass
class QuorumResult:
    outcome: str                       # "QUORUM_REACHED" | "NO_QUORUM" | "SPLIT"
    decided_verdict: Optional[Any]
    config: dict
    reachable: int
    total: int
    tally: dict
    agreement_threshold: int
    min_total: int
    votes: list[dict]
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "decided_verdict": self.decided_verdict,
            "config": self.config,
            "reachable": self.reachable,
            "total": self.total,
            "tally": self.tally,
            "agreement_threshold": self.agreement_threshold,
            "min_total": self.min_total,
            "byzantine_safe": self.reachable >= self.min_total,
            "votes": self.votes,
            "reason": self.reason,
        }


def decide(votes: list[OrganVote], config: Optional[QuorumConfig] = None) -> QuorumResult:
    """Run the Byzantine quorum decision over a set of organ votes.

    Returns QUORUM_REACHED with the agreed verdict iff at least 2f+1 reachable
    organs report the SAME verdict AND at least 3f+1 organs are reachable.
    """
    cfg = config or QuorumConfig()
    total = len(votes)
    reachable_votes = [v for v in votes if v.reachable and v.verdict is not None]
    reachable = len(reachable_votes)
    thr = cfg.agreement_threshold()
    min_total = cfg.min_total()

    tally = Counter(_key(v.verdict) for v in reachable_votes)
    tally_d = dict(tally)
    votes_d = [{"organ": v.organ, "reachable": v.reachable,
                "verdict": v.verdict, "receipt_hash": v.receipt_hash} for v in votes]

    base = dict(
        config={"n": cfg.n, "f": cfg.f, "byzantine_safe_config": cfg.tolerates_byzantine()},
        reachable=reachable, total=total, tally=tally_d,
        agreement_threshold=thr, min_total=min_total, votes=votes_d,
    )

    # 0. FAIL-CLOSED on an ill-formed / adversarial config BEFORE any tally.
    #    A negative fault budget f makes the agreement threshold 2f+1 <= 0, which
    #    the "top_count >= thr" test below would treat as trivially satisfied —
    #    letting a SINGLE organ (or none) forge QUORUM_REACHED. We refuse to decide
    #    on such a config and return NO_QUORUM with a disclosed reason; Byzantine
    #    safety is never fabricated from a config that cannot provide it.
    if not cfg.is_valid():
        return QuorumResult(
            outcome="NO_QUORUM", decided_verdict=None, **base,
            reason=(f"ill-formed quorum config (n={cfg.n}, f={cfg.f}): requires "
                    f"f >= 0 and n >= 1 with positive thresholds "
                    f"(2f+1={thr}, 3f+1={min_total}). Fail-closed; Byzantine "
                    "safety not fabricated."),
        )

    if reachable < min_total:
        return QuorumResult(
            outcome="NO_QUORUM", decided_verdict=None, **base,
            reason=(f"only {reachable} organ(s) reachable; Byzantine safety needs "
                    f">= {min_total} (3f+1, f={cfg.f}). Disclosed, not forced."),
        )

    if not tally:
        return QuorumResult(outcome="NO_QUORUM", decided_verdict=None, **base,
                            reason="no organ returned a verdict.")

    top_key, top_count = tally.most_common(1)[0]
    if top_count >= thr:
        decided = next(v.verdict for v in reachable_votes if _key(v.verdict) == top_key)
        return QuorumResult(
            outcome="QUORUM_REACHED", decided_verdict=decided, **base,
            reason=(f"{top_count}/{reachable} organs agree (>= 2f+1 = {thr}); "
                    f"{reachable} reachable (>= 3f+1 = {min_total})."),
        )

    return QuorumResult(
        outcome="SPLIT", decided_verdict=None, **base,
        reason=(f"reachable={reachable} (>= {min_total}) but no verdict reached the "
                f"agreement threshold {thr}; top was {top_count}. No safe decision."),
    )


def _key(verdict: Any) -> str:
    """Canonical hashable key for a verdict value (for tallying)."""
    if isinstance(verdict, (dict, list)):
        import json
        return json.dumps(verdict, sort_keys=True, separators=(",", ":"))
    return str(verdict)
