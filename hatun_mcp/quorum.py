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

import json
import math
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

ORGANS = ("a11oy", "llm", "immune", "killinchu", "companion")


@dataclass(frozen=True)
class QuorumConfig:
    n: int = 5
    f: int = 1
    participants: tuple[str, ...] = ORGANS

    def tolerates_byzantine(self) -> bool:
        """True iff the complete configuration can safely tolerate ``f`` faults."""
        return _config_error(self) is None

    def min_total(self) -> int:
        """Minimum number of reachable participants for a valid quorum: 3f+1."""
        return 3 * self.f + 1 if type(self.f) is int else 0

    def agreement_threshold(self) -> int:
        """Matching-verdict count required to decide: 2f+1."""
        return 2 * self.f + 1 if type(self.f) is int else 0

    def is_valid(self) -> bool:
        """True iff this is a well-formed Byzantine config that decide() may act on.

        Requires a NON-NEGATIVE fault budget f, at least one participant, and
        n >= 3f+1. A negative f is rejected FAIL-CLOSED because it makes the
        agreement threshold trivial. An undersized n cannot provide the stated
        Byzantine tolerance. Neither condition may be presented as safe.
        """
        return _config_error(self) is None


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
            "byzantine_safe": (
                bool(self.config.get("byzantine_safe_config"))
                and bool(self.config.get("participant_set_valid"))
                and self.reachable >= self.min_total
            ),
            "votes": self.votes,
            "reason": self.reason,
        }


def decide(votes: list[OrganVote], config: Optional[QuorumConfig] = None) -> QuorumResult:
    """Run the Byzantine quorum decision over a set of organ votes.

    Returns QUORUM_REACHED with the agreed verdict iff at least 2f+1 reachable
    organs report the SAME verdict AND at least 3f+1 organs are reachable.
    """
    cfg = config if config is not None else QuorumConfig()
    config_error = _config_error(cfg)
    vote_items = votes if type(votes) is list else []
    total = len(vote_items)
    # Invalid configs must not leak attacker-sized arithmetic into the result
    # envelope; keep fail-closed responses bounded and JSON serializable.
    thr = cfg.agreement_threshold() if config_error is None else 0
    min_total = cfg.min_total() if config_error is None else 0
    votes_d = [_safe_vote_dict(vote) for vote in vote_items]

    # Participant identity is part of the safety boundary. Without this check,
    # the same organ can be submitted repeatedly and forge a 2f+1 tally.
    participant_error = (
        _validate_participants(vote_items, cfg)
        if config_error is None and type(votes) is list
        else ("votes must be a list" if type(votes) is not list else None)
    )

    if config_error is None and participant_error is None:
        reachable_votes = [v for v in vote_items if v.reachable]
        reachable = len(reachable_votes)
        tally = Counter(_key(v.verdict) for v in reachable_votes)
    else:
        reachable_votes = []
        reachable = 0
        tally = Counter()
    tally_d = dict(tally)

    base = dict(
        config=_safe_config_dict(cfg, config_error, participant_error),
        reachable=reachable, total=total, tally=tally_d,
        agreement_threshold=thr, min_total=min_total, votes=votes_d,
    )

    # 0. FAIL-CLOSED on an ill-formed / adversarial config BEFORE any tally.
    #    A negative fault budget f makes the agreement threshold 2f+1 <= 0, which
    #    the "top_count >= thr" test below would treat as trivially satisfied —
    #    letting a SINGLE organ (or none) forge QUORUM_REACHED. We refuse to decide
    #    on such a config and return NO_QUORUM with a disclosed reason; Byzantine
    #    safety is never fabricated from a config that cannot provide it.
    if config_error:
        return QuorumResult(
            outcome="NO_QUORUM", decided_verdict=None, **base,
            reason=f"ill-formed quorum config: {config_error}. Fail-closed.",
        )

    if participant_error:
        return QuorumResult(
            outcome="NO_QUORUM", decided_verdict=None, **base,
            reason=f"invalid participant set: {participant_error}. Fail-closed.",
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
    """Return a type-preserving canonical key for a JSON verdict.

    ``str(verdict)`` is unsafe here: ``True`` and ``"True"`` collide, as do a
    JSON object and a string containing that object's JSON spelling. A quorum
    tally must count semantically identical verdicts only.
    """
    error = _json_domain_error(verdict, "verdict")
    if error:
        raise ValueError(error)
    return json.dumps(
        {"type": type(verdict).__name__, "value": verdict},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _config_error(cfg: Any) -> Optional[str]:
    """Return a total, exception-free explanation for an unsafe config."""
    if type(cfg) is not QuorumConfig:
        return f"config must be QuorumConfig, got {type(cfg).__name__}"
    if type(cfg.n) is not int or type(cfg.f) is not int:
        return "n and f must be exact non-boolean integers"
    if cfg.f < 0 or cfg.n < 1:
        return "f must be >= 0 and n must be >= 1"
    if cfg.n > 4096 or cfg.f > 1365:
        return "n and f must be within bounded participant limits"
    if cfg.n < 3 * cfg.f + 1:
        return f"n={cfg.n} cannot satisfy n >= 3f+1 for f={cfg.f}"
    if type(cfg.participants) is not tuple:
        return "participants must be an immutable tuple"
    if len(cfg.participants) != cfg.n:
        return f"participants length {len(cfg.participants)} does not equal n={cfg.n}"

    seen: set[str] = set()
    for participant in cfg.participants:
        identity, error = _participant_identity(participant)
        if error:
            return f"invalid configured participant: {error}"
        if identity in seen:
            return f"duplicate configured participant {participant!r}"
        seen.add(identity)
    return None


def _validate_participants(votes: list[OrganVote], cfg: QuorumConfig) -> Optional[str]:
    """Validate identity, metadata, and JSON-domain verdicts for every vote."""
    if len(votes) > cfg.n:
        return f"received {len(votes)} votes for configured n={cfg.n}"

    expected = {_participant_identity(name)[0] for name in cfg.participants}
    seen: set[str] = set()
    for vote in votes:
        if type(vote) is not OrganVote:
            return f"vote must be OrganVote, got {type(vote).__name__}"
        identity, error = _participant_identity(vote.organ)
        if error:
            return error
        if identity not in expected:
            return f"organ {vote.organ!r} is outside the configured participant registry"
        if identity in seen:
            return f"duplicate organ identity {vote.organ!r}"
        seen.add(identity)
        if type(vote.reachable) is not bool:
            return f"reachable for {vote.organ!r} must be a boolean"
        if vote.reachable and vote.verdict is None:
            return f"reachable organ {vote.organ!r} did not provide a verdict"
        if not vote.reachable and vote.verdict is not None:
            return f"unreachable organ {vote.organ!r} provided a verdict"
        if vote.reachable:
            error = _json_domain_error(vote.verdict, f"verdict[{vote.organ}]")
            if error:
                return error
        if vote.receipt_hash is not None and type(vote.receipt_hash) is not str:
            return f"receipt_hash for {vote.organ!r} must be a string or null"
    return None


def _safe_verdict(verdict: Any) -> Any:
    """Keep failure results JSON-serializable even for adversarial verdicts."""
    error = _json_domain_error(verdict, "verdict")
    return verdict if error is None else {"invalid_verdict": error}


def _safe_vote_dict(vote: Any) -> dict:
    if type(vote) is not OrganVote:
        return {"invalid_vote_type": type(vote).__name__}
    return {
        "organ": _safe_json_value(vote.organ, "organ"),
        "reachable": _safe_json_value(vote.reachable, "reachable"),
        "verdict": _safe_verdict(vote.verdict),
        "receipt_hash": _safe_json_value(vote.receipt_hash, "receipt_hash"),
    }


def _safe_config_dict(
    cfg: Any, config_error: Optional[str], participant_error: Optional[str]
) -> dict:
    if type(cfg) is not QuorumConfig:
        return {
            "invalid_config_type": type(cfg).__name__,
            "byzantine_safe_config": False,
            "participant_set_valid": False,
        }
    participants = (
        list(cfg.participants)
        if type(cfg.participants) is tuple
        else _safe_json_value(cfg.participants, "participants")
    )
    return {
        "n": _safe_json_value(cfg.n, "n"),
        "f": _safe_json_value(cfg.f, "f"),
        "participants": _safe_json_value(participants, "participants"),
        "byzantine_safe_config": config_error is None,
        "participant_set_valid": config_error is None and participant_error is None,
    }


def _safe_json_value(value: Any, path: str) -> Any:
    error = _json_domain_error(value, path)
    return value if error is None else {"invalid_value": error}


def _json_domain_error(value: Any, path: str) -> Optional[str]:
    """Require exact JSON types recursively; reject Python coercion collisions."""
    return _json_domain_error_inner(value, path, set(), 0, [0])


def _json_domain_error_inner(
    value: Any, path: str, ancestors: set[int], depth: int, nodes: list[int]
) -> Optional[str]:
    nodes[0] += 1
    if nodes[0] > 4096:
        return f"{path} exceeds the 4096-node verdict limit"
    if depth > 32:
        return f"{path} exceeds the 32-level verdict depth limit"

    value_type = type(value)
    if value is None or value_type in (str, bool):
        return None
    if value_type is int:
        if -(2**63) <= value <= 2**63 - 1:
            return None
        return f"{path} contains an integer outside the signed 64-bit range"
    if value_type is float:
        return None if math.isfinite(value) else f"{path} contains a non-finite float"
    if value_type is list:
        identity = id(value)
        if identity in ancestors:
            return f"{path} contains a cyclic list"
        ancestors.add(identity)
        try:
            for index, item in enumerate(value):
                error = _json_domain_error_inner(
                    item, f"{path}[{index}]", ancestors, depth + 1, nodes
                )
                if error:
                    return error
        finally:
            ancestors.remove(identity)
        return None
    if value_type is dict:
        identity = id(value)
        if identity in ancestors:
            return f"{path} contains a cyclic object"
        ancestors.add(identity)
        try:
            for key, item in value.items():
                if type(key) is not str:
                    return f"{path} has non-string object key of type {type(key).__name__}"
                error = _json_domain_error_inner(
                    item, f"{path}.{key}", ancestors, depth + 1, nodes
                )
                if error:
                    return error
        finally:
            ancestors.remove(identity)
        return None
    return f"{path} has unsupported type {value_type.__name__}"


def _participant_identity(value: Any) -> tuple[Optional[str], Optional[str]]:
    if type(value) is not str or not value:
        return None, "organ identifiers must be non-empty strings"
    if value != value.strip():
        return None, f"organ identifier {value!r} has surrounding whitespace"
    normalized = unicodedata.normalize("NFKC", value)
    if normalized != value:
        return None, f"organ identifier {value!r} is not NFKC-normalized"
    return normalized.casefold(), None
