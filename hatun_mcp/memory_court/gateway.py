"""Memory Court gateway: the fail-closed admission pipeline (day-4).

Day-4 closes the TOCTOU trust gap flagged in the two-brain adversarial
review of day-3 (mistral-large-4:cloud + qwen2.5-coder:7b) and hardened
after the day-4 design review (GPT-6 via the ChatGPT app +
mistral-large-4:cloud, 2026-11-20, both verdicts FIX-FIRST):

    operator-auth -> tenant bind -> routing-header check -> memory-id check
    -> idempotency-key required -> build attestation
    -> trust-root SNAPSHOT (one per invoke; provider failure => refuse)
    -> idempotency replay (trust-bound; legacy/rotated refuse)
    -> adjudication whitelist -> sign (validated; key id in snapshot)
    -> signature verification (when a verifier is injected)
    -> preconditioned khipu append (digest re-assert inside the commit)
    -> dependent writes only after commit

Day-4 invariants (each with a contract test):
- ONE snapshot per invoke; version, build digest, signer key ids and a
  monotonic epoch are bound into snapshot_digest (ABA-proof).
- v1 receipts carry mandatory trust bindings; nothing half-signed or
  half-bound ever commits (empty v1 fields are refused at build).
- The signer returns (signature, key_id); key_id must be in the
  snapshot's signer_key_ids or nothing signs or commits.
- The signature covers the FULL v1 envelope (signed_payload); when a
  signature_verifier is injected, verification must pass before the
  commit (DSSE against owner keys remains ROADMAP).
- The append precondition re-asserts the CURRENT snapshot digest inside
  the commit lock; rotation between sign and commit => 503
  trust_root_rotated, nothing committed.
- Replay: v0 receipts are read-only legacy and refuse to replay (their
  trust binding is UNKNOWN); a receipt committed under a different
  snapshot digest or a rotated-out signer key refuses with 503
  trust_root_rotated. Replays return committed evidence only and are
  NEVER re-adjudicated or re-signed. Re-adjudication under a rotated
  root requires a fresh request through the full pipeline.

Day-3 hardening retained (receipts semantics locked):
- No commit path without an idempotency key; adjudication whitelist
  (admit/abstain only); replay binds request identity (409 on mismatch);
  admission replay re-releases its dependent write (idempotent by
  event_id); nothing commits unsigned; append failure is 503
  signed-uncommitted, never success; an existing khipu entry is the
  SOLE success proof for an interrupted request.

Replay-of-old-root policy note: GPT-6 suggested a conditional historical
allow under an explicit historical-trust policy; mistral-large-4 refused.
Fail-closed resolves the conflict toward refusal until the owner adopts
an explicit historical trust policy (ROADMAP, owner-gated).

All infrastructure (auth, tenant resolution, build attestation, trust
root, signer, verifier, khipu writer) is injected so the contract is
testable without production key material (owner-gated, ROADMAP).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .khipu_writer import KhipuPreconditionError
from .receipts import (
    AdmissibilityReceiptV1,
    RECEIPT_SCHEMA,
    build_receipt_v1,
    canonical_sha256,
    signed_payload,
)
from .trust_root import TrustRootError

__all__ = [
    "MemoryCourtGateway",
    "Outcome",
    "Request",
    "SignerKeyUnknown",
    "SignerUnavailable",
]


class SignerKeyUnknown(Exception):
    """The presented signer key id is not in the active trust root."""


class SignerUnavailable(Exception):
    """No signer could be reached; nothing may be committed."""


@dataclass(frozen=True)
class Request:
    tool: str
    args: Dict[str, Any]
    operator_subject: Optional[str] = None
    tenant: Optional[str] = None
    routing_headers: Dict[str, str] = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    memory_id: str = ""


@dataclass(frozen=True)
class Outcome:
    status: int
    reason: str
    receipt_kind: Optional[str] = None  # "admission" | "abstention" | "signed-uncommitted" | None
    committed_receipt: Optional[AdmissibilityReceiptV1] = None
    dependent_writes: List[str] = field(default_factory=list)


REQUIRED_ROUTING_HEADERS = ("mcp-session-id", "mcp-profile")
ADMITTED_DECISIONS = frozenset({"admit", "abstain"})


class MemoryCourtGateway:
    """Fail-closed admission gate. Every failure stops dependent writes."""

    def __init__(
        self,
        *,
        auth: Callable[[Optional[str]], bool],
        tenant_resolver: Callable[[Optional[str]], bool],
        build_admissible: Callable[[], bool],
        trust_root,  # object with .snapshot() -> TrustSnapshot
        adjudicator: Callable[[Request], str],  # "admit" | "abstain" | "block"
        signer: Callable[[AdmissibilityReceiptV1], Tuple[str, str]],  # (signature, key_id)
        khipu,  # object with .get / .append_with_precondition
        signature_verifier: Optional[Callable[[str, str, str], bool]] = None,
    ) -> None:
        self._auth = auth
        self._tenants = tenant_resolver
        self._build_ok = build_admissible
        self._trust_root = trust_root
        self._adjudicator = adjudicator
        self._signer = signer
        self._khipu = khipu
        self._verifier = signature_verifier

    # -- pipeline ---------------------------------------------------------

    def invoke(self, request: Request) -> Outcome:
        if not self._auth(request.operator_subject):
            return Outcome(401, "operator_auth_failed")

        if not self._tenants(request.tenant):
            return Outcome(403, "tenant_mismatch")

        for header in REQUIRED_ROUTING_HEADERS:
            value = request.routing_headers.get(header)
            if not value or not str(value).strip():
                return Outcome(400, "malformed_routing_headers")

        if not request.memory_id or not str(request.memory_id).strip():
            return Outcome(400, "memory_id_required")

        if not request.idempotency_key or not str(request.idempotency_key).strip():
            # A claim without a commit anchor is a LEAK: refuse, never admit.
            return Outcome(503, "idempotency_key_required")

        if not self._build_ok():
            return Outcome(503, "build_not_admissible")

        # ONE snapshot per invoke; sampled once, bound everywhere.
        try:
            snap = self._trust_root.snapshot()
        except TrustRootError:
            # Unknown/invalid root (incl. no signers): nothing is signed.
            return Outcome(503, "trust_root_version_unknown")
        except Exception:
            # Provider crash: unknown state is a refusal, never a fallback.
            return Outcome(503, "trust_root_unavailable")

        # Identity-bound digest: domain-separates event ids per tenant/key
        # and gives the replay check something real to compare.
        request_digest = canonical_sha256(
            {
                "tool": request.tool,
                "args": request.args,
                "tenant": request.tenant,
                "memory_id": request.memory_id,
                "idempotency_key": request.idempotency_key,
            }
        )

        # Recovery rule: an existing khipu entry is the sole success proof.
        existing = self._khipu.get(request.idempotency_key)
        if existing is not None:
            same_request = (
                existing.operation == request.tool
                and existing.memory_id == request.memory_id
                and existing.tenant == request.tenant
                and existing.request_digest == request_digest
            )
            if not same_request:
                # Same key, different request: poisoning vector, refuse.
                return Outcome(409, "idempotency_conflict")
            if existing.schema == RECEIPT_SCHEMA:
                # Legacy v0: trust binding is UNKNOWN; read-only, never
                # replayed as success (fail-closed).
                return Outcome(503, "receipt_legacy_refused")
            if (
                getattr(existing, "snapshot_digest", "") != snap.digest
                or getattr(existing, "signer_key_id", "") not in snap.signer_key_ids
            ):
                # Committed under a different root: refuse. Conditional
                # historical replay needs an owner-adopted policy (ROADMAP).
                return Outcome(503, "trust_root_rotated")
            if existing.decision == "abstain":
                return Outcome(
                    200,
                    "replayed_original_receipt",
                    receipt_kind="abstention",
                    committed_receipt=existing,
                )
            if existing.decision != "admit":
                # Stored receipt outside the whitelist: refuse, never assume.
                return Outcome(503, "stored_receipt_invalid")
            return Outcome(
                200,
                "replayed_original_receipt",
                receipt_kind="admission",
                committed_receipt=existing,
                # Re-release: a crash between commit and release must not
                # strand the dependent write. Idempotent by event_id.
                dependent_writes=["released:" + existing.event_id],
            )

        decision = self._adjudicator(request)
        if decision == "block":
            return Outcome(503, "adjudication_blocked")
        if decision not in ADMITTED_DECISIONS:
            # Unknown stays UNKNOWN: never fall through to admission.
            return Outcome(503, "adjudication_unknown")

        # v1 envelope: mandatory trust bindings, refusals at build time.
        try:
            receipt = build_receipt_v1(
                operation=request.tool,
                memory_id=request.memory_id,
                operator_subject=request.operator_subject or "",
                tenant=request.tenant or "",
                request_digest=request_digest,
                decision=decision,
                trust_root_version=snap.version,
                build_digest=snap.build_digest,
                snapshot_digest=snap.digest,
            )
        except ValueError:
            return Outcome(503, "receipt_envelope_invalid")

        try:
            signature, key_id = self._signer(receipt)
        except SignerKeyUnknown:
            return Outcome(503, "signer_key_unknown")
        except SignerUnavailable:
            return Outcome(503, "signer_unavailable")
        except Exception:
            # Generic signer failure: nothing committed (fail-closed).
            return Outcome(503, "signer_error")

        if not isinstance(signature, str) or not signature.strip():
            # An empty signature would fabricate evidence: refuse.
            return Outcome(503, "signer_invalid_signature")
        if not isinstance(key_id, str) or not key_id.strip():
            # A signature without a bound key id is unverifiable: refuse.
            return Outcome(503, "signer_key_unknown")
        if key_id not in snap.signer_key_ids:
            # Forged/rotated-out key id: nothing signs on our watch.
            return Outcome(503, "signer_key_unknown")

        payload = signed_payload(receipt)
        if self._verifier is not None:
            try:
                verified = self._verifier(payload, signature, key_id)
            except Exception:
                return Outcome(503, "signature_verification_failed")
            if not verified:
                # Signature does not cover the envelope as claimed.
                return Outcome(503, "signature_verification_failed")

        try:
            signed = AdmissibilityReceiptV1(
                schema=receipt.schema,
                operation=receipt.operation,
                event_id=receipt.event_id,
                memory_id=receipt.memory_id,
                ts=receipt.ts,
                operator_subject=receipt.operator_subject,
                tenant=receipt.tenant,
                request_digest=receipt.request_digest,
                canonicalization=receipt.canonicalization,
                gate=receipt.gate,
                decision=receipt.decision,
                astype_signature=signature,
                status_current=receipt.status_current,
                trust_root_version=receipt.trust_root_version,
                build_digest=receipt.build_digest,
                signer_key_id=key_id,
                snapshot_digest=receipt.snapshot_digest,
            )
        except Exception:
            return Outcome(503, "signer_invalid_signature")

        try:
            self._khipu.append_with_precondition(
                request.idempotency_key,
                signed,
                expect_snapshot_digest=snap.digest,
                current_snapshot_digest=lambda: self._trust_root.snapshot().digest,
            )
        except KhipuPreconditionError:
            # The root rotated (or became unreadable) between sign and
            # commit: nothing was written, nothing releases.
            return Outcome(
                503,
                "trust_root_rotated",
                receipt_kind="signed-uncommitted",
            )
        except Exception:
            # Signed but uncommitted: internal evidence only, never success.
            # Broad catch is deliberate (any append failure must refuse);
            # BaseException (KeyboardInterrupt/SystemExit) still propagates.
            return Outcome(
                503,
                "receipt_commit_failed",
                receipt_kind="signed-uncommitted",
            )

        if decision == "abstain":
            # Abstention is committed - but it is not an allow.
            return Outcome(
                200,
                "adjudication_abstained",
                receipt_kind="abstention",
                committed_receipt=signed,
            )

        return Outcome(
            200,
            "admitted",
            receipt_kind="admission",
            committed_receipt=signed,
            dependent_writes=["released:" + receipt.event_id],
        )
