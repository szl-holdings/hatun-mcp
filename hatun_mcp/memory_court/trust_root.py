"""Trust root provider + immutable snapshot (day-4 slice, PR follow-up to #205).

Design hardened after the two-brain adversarial review of the day-4
trust-root design (GPT-6 via the ChatGPT desktop app + mistral-large-4:cloud,
2026-11-20, both verdicts FIX-FIRST; transcripts runtime/transcripts/
gpt6_trustroot_rev_transcript.md + mistral_trustroot_rev_transcript.md):

- The gateway samples ONE snapshot per invoke; `snapshot()` is the only
  trust-root read path, and the snapshot DIGEST (not just its version) is
  what the commit precondition re-asserts (prevents version reuse / ABA).
- version + build_digest + epoch + signer_key_ids are all bound into
  `snapshot_digest`; a reused version string under changed keys or build
  identity produces a different digest, so a version collision cannot
  satisfy the writer precondition (review finding MEDIUM/HIGH).
- An empty signer_key_ids set is INVALID (fail-closed): the gate refuses
  rather than treating an empty trust set as "anything goes" (LOW finding).
- Provider failure is refusal (503), never a silent fallback. Trust-root
  rotation is serialized behind a strictly monotonic epoch (GPT-6 finding:
  rotation must be transactionally bound; Mistral finding: rotation must
  not race the writer lock - the gateway re-asserts the digest inside the
  append boundary in khipu_writer.append_with_precondition).

Production trust-root material is owner-gated (ROADMAP); this module
defines the provider BOUNDARY plus a static in-process implementation
used by the contract tests. No secrets live here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import FrozenSet

__all__ = ["TrustSnapshot", "TrustRootError", "StaticTrustRoot"]

SNAPSHOT_DIGEST_VERSION = "szl.trust-snapshot/v1"


class TrustRootError(Exception):
    """The trust root is unknown, structurally invalid, or regressed."""


@dataclass(frozen=True)
class TrustSnapshot:
    """Immutable view of the active trust root. Never mutated in flight."""

    version: str
    build_digest: str
    signer_key_ids: FrozenSet[str]
    epoch: int

    @property
    def digest(self) -> str:
        payload = "|".join(
            (
                SNAPSHOT_DIGEST_VERSION,
                self.version,
                self.build_digest,
                str(self.epoch),
                ",".join(sorted(self.signer_key_ids)),
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def validate(self) -> None:
        """A snapshot without identity or keys is not a trust root."""
        if not self.version or not str(self.version).strip():
            raise TrustRootError("trust_root_version_empty")
        if not self.build_digest or not str(self.build_digest).strip():
            raise TrustRootError("trust_root_build_digest_empty")
        if not self.signer_key_ids:
            # An empty trust set would silently admit anything: refuse.
            raise TrustRootError("trust_root_no_signers")


class StaticTrustRoot:
    """In-process provider for tests; rotate by swapping the snapshot.

    Rotation semantics (review finding: version ABA / rollback):
    - `rotate()` enforces a strictly monotonic epoch, so a rollback to an
      older epoch is refused by the provider itself (never re-authorized).
    - Reusing a version string under changed keys/build is representable
      only as an explicit new snapshot with a new epoch; its digest differs,
      so in-flight requests fail the writer precondition and stored
      receipts fail the replay trust check.
    """

    def __init__(self, snapshot: TrustSnapshot) -> None:
        self._snapshot = snapshot
        self._ceiling_epoch = snapshot.epoch

    def snapshot(self) -> TrustSnapshot:
        snap = self._snapshot
        snap.validate()  # the provider never hands out an invalid root
        return snap

    def rotate(self, snapshot: TrustSnapshot) -> None:
        snapshot.validate()
        if snapshot.epoch <= self._ceiling_epoch:
            raise TrustRootError("trust_root_epoch_regression")
        self._ceiling_epoch = snapshot.epoch
        self._snapshot = snapshot
