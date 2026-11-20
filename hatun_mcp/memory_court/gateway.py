"""Memory Court gateway: the fail-closed admission pipeline.

Implements the day-2 decision table (docs/memory-court/MEMORY_COURT_DAY2.md):

    operator-auth -> tenant bind -> routing-header check -> build attestation
    -> trust root -> idempotency replay -> adjudication -> sign -> khipu append

Receipt semantics (locked):
- `None` kind: no receipt object is emitted.
- `abstention`: committed only AFTER signing and khipu append.
- `signed-uncommitted`: internal evidence of a failed khipu commit; it is
  never a success receipt.
- Recovery rule: an existing khipu entry is the SOLE success proof for an
  interrupted request; absence of an entry means abort, not inferred success.

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
    memory_id: str = "mem_pending"


@dataclass(frozen=True)
class Outcome:
    status: int
    reason: str
    receipt_kind: Optional[str] = None  # "admission" | "abstention" | "signed-uncommitted" | None
    committed_receipt: Optional[AdmissibilityReceipt] = None
    dependent_writes: List[str] = field(default_factory=list)


REQUIRED_ROUTING_HEADERS = ("mcp-session-id", "mcp-profile")


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

        if not self._build_ok():
            return Outcome(503, "build_not_admissible")

        if not self._trust_root_ok():
            return Outcome(503, "trust_root_version_unknown")

        # Recovery rule: an existing khipu entry is the sole success proof.
        if request.idempotency_key is not None:
            existing = self._khipu.get(request.idempotency_key)
            if existing is not None:
                kind = "abstention" if existing.decision == "abstain" else "admission"
                return Outcome(
                    200,
                    "replayed_original_receipt",
                    receipt_kind=kind,
                    committed_receipt=existing,
                )

        decision = self._adjudicator(request)
        if decision == "block":
            return Outcome(503, "adjudication_blocked")

        receipt = build_receipt(
            operation=request.tool,
            memory_id=request.memory_id,
            operator_subject=request.operator_subject or "",
            tenant=request.tenant or "",
            request_digest=canonical_sha256({"tool": request.tool, "args": request.args}),
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

        if request.idempotency_key is not None:
            try:
                self._khipu.append(request.idempotency_key, signed)
            except Exception:
                # Signed but uncommitted: internal evidence only, never success.
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
