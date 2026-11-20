"""Memory Court gateway: the fail-closed admission pipeline.

Implements the day-2 decision table (docs/memory-court/MEMORY_COURT_DAY2.md)
as hardened after the two-brain adversarial review (mistral-large-4:cloud
+ qwen2.5-coder:7b, 2026-11-20, both verdicts FIX-FIRST):

    operator-auth -> tenant bind -> routing-header check -> memory-id check
    -> idempotency-key required -> build attestation -> trust root
    -> idempotency replay -> adjudication whitelist -> sign (validated)
    -> khipu append

Hardening invariants added after review (each has a contract test):
- No commit path exists without an idempotency key: key=None is refused
  (503 idempotency_key_required). A claim without a commit anchor is a LEAK.
- Adjudication whitelist: only "admit"/"abstain" proceed; "block" and every
  other/unknown decision value refuse (unknown stays UNKNOWN).
- Replay binds request identity (operation, memory_id, tenant, digest):
  same key + different request => 409 idempotency_conflict, never a silent
  old-receipt pass-through. The digest itself binds tool/args/tenant/
  memory_id/idempotency_key, so event ids are domain-separated per tenant
  and per key.
- Replay of an admission re-releases its dependent write (idempotent by
  event_id): a crash between commit and release no longer strands the write.
- Signer output is validated (non-empty signature required); generic signer
  failures refuse with 503 signer_error. Nothing commits unsigned/unverified.

Receipt semantics (locked):
- `None` kind: no receipt object is emitted on refusals.
- `abstention`: committed only AFTER signing and khipu append; it is never
  an allow and releases no dependent writes.
- `signed-uncommitted`: internal evidence of a failed khipu commit; it is
  never a success receipt and never populates committed_receipt.
- Recovery rule: an existing khipu entry is the SOLE success proof for an
  interrupted request; absence of an entry means abort, not inferred success.

TOCTOU (review finding, wrapper contract): auth/tenant/build/trust are
sampled before commit, and commit happens later. The production wrapper
must re-assert them atomically with the khipu append and bind the build
digest, trust-root version and signer key id into the receipt envelope;
that is the trust-root work in the ROADMAP, not this slice.

All infrastructure (auth, tenant resolution, trust root, build attestation,
signer, khipu writer) is injected so the contract is testable without
production key material (which is owner-gated, ROADMAP).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .receipts import AdmissibilityReceipt, build_receipt, canonical_sha256

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
    committed_receipt: Optional[AdmissibilityReceipt] = None
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
        trust_root_ok: Callable[[], bool],
        adjudicator: Callable[[Request], str],  # "admit" | "abstain" | "block"
        signer: Callable[[AdmissibilityReceipt], str],  # returns signature
        khipu,  # object with .get(key) / .append(key, receipt)
    ) -> None:
        self._auth = auth
        self._tenants = tenant_resolver
        self._build_ok = build_admissible
        self._trust_root_ok = trust_root_ok
        self._adjudicator = adjudicator
        self._signer = signer
        self._khipu = khipu

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

        if not self._trust_root_ok():
            return Outcome(503, "trust_root_version_unknown")

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

        receipt = build_receipt(
            operation=request.tool,
            memory_id=request.memory_id,
            operator_subject=request.operator_subject or "",
            tenant=request.tenant or "",
            request_digest=request_digest,
            decision=decision,
            signature="",
            status_current="admissible",
        )

        try:
            signature = self._signer(receipt)
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

        signed = build_receipt(
            operation=receipt.operation,
            memory_id=receipt.memory_id,
            operator_subject=receipt.operator_subject,
            tenant=receipt.tenant,
            request_digest=receipt.request_digest,
            decision=receipt.decision,
            signature=signature,
            status_current="admissible",
        )

        try:
            self._khipu.append(request.idempotency_key, signed)
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
