"""Admissibility receipt construction and canonical digests (v0 + v1).

Day-4 v1 envelope, hardened after the two-brain adversarial review
(GPT-6 via the ChatGPT app + mistral-large-4:cloud, 2026-11-20, both
verdicts FIX-FIRST):

- v1 receipts carry MANDATORY trust-binding fields
  (trust_root_version, build_digest, signer_key_id, snapshot_digest).
  They are nonempty for every new write; empty-string defaults are
  refused at build time (HIGH finding: silent incomplete receipts).
- The event_id binds the snapshot digest, so the same logical request
  under two different trust roots can never alias (HIGH finding:
  cross-root event_id collision would let an old-root receipt replay
  as success).
- `signed_payload()` domain-separates and covers the FULL v1 envelope
  (minus the signature itself): CRITICAL finding - a signature must
  cover trust_root_version, build_digest, tenant, decision and request
  identity, or post-commit field edits are undetectable without DSSE.
- v0 receipts remain LOADABLE (read-only legacy for audit) but are never
  written again: the gateway builds only v1, and the writer refuses a
  v0 append (schema discrimination, HIGH finding).

Canonicalization note: this slice uses deterministic stdlib JSON
(sort_keys, compact separators, ensure_ascii=False) as a documented
simplification of JCS (RFC 8785). The digest field records the form.
No number or receipt is ever fabricated here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict

RECEIPT_SCHEMA = "szl.memory-admissibility-receipt/v0"
RECEIPT_SCHEMA_V1 = "szl.memory-admissibility-receipt/v1"
CANONICALIZATION = "stdlib-json-sortkeys-v1"
SIGNED_PAYLOAD_DOMAIN = "szl.memory-admissibility/v1"


def canonical_sha256(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True)
class AdmissibilityReceipt:
    """Legacy v0 record (day-3). Read-only: never written by the gateway."""

    schema: str
    operation: str
    event_id: str
    memory_id: str
    ts: str
    operator_subject: str
    tenant: str
    request_digest: str
    canonicalization: str
    gate: str
    decision: str
    astype_signature: str
    status_current: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["signature"] = d.pop("astype_signature")
        return d


@dataclass(frozen=True)
class AdmissibilityReceiptV1:
    """v1 receipt: the v0 envelope plus mandatory trust bindings."""

    schema: str
    operation: str
    event_id: str
    memory_id: str
    ts: str
    operator_subject: str
    tenant: str
    request_digest: str
    canonicalization: str
    gate: str
    decision: str
    astype_signature: str
    status_current: str
    trust_root_version: str
    build_digest: str
    signer_key_id: str
    snapshot_digest: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["signature"] = d.pop("astype_signature")
        return d


def build_receipt(
    *,
    operation: str,
    memory_id: str,
    operator_subject: str,
    tenant: str,
    request_digest: str,
    decision: str,
    signature: str,
    status_current: str = "admissible",
) -> AdmissibilityReceipt:
    """LEGACY v0 builder. Kept only for read-side/audit compatibility."""
    return AdmissibilityReceipt(
        schema=RECEIPT_SCHEMA,
        operation=operation,
        event_id=(
            "evt_"
            + hashlib.sha256(
                (memory_id + request_digest + decision).encode("utf-8")
            ).hexdigest()[:24]
        ),
        memory_id=memory_id,
        ts=utc_now_iso(),
        operator_subject=operator_subject,
        tenant=tenant,
        request_digest=request_digest,
        canonicalization=CANONICALIZATION,
        gate="yuyay-13",
        decision=decision,
        astype_signature=signature,
        status_current=status_current,
    )


def build_receipt_v1(
    *,
    operation: str,
    memory_id: str,
    operator_subject: str,
    tenant: str,
    request_digest: str,
    decision: str,
    trust_root_version: str,
    build_digest: str,
    snapshot_digest: str,
    signer_key_id: str = "",
    signature: str = "",
    status_current: str = "admissible",
) -> AdmissibilityReceiptV1:
    """Build a v1 receipt (unsigned, or signed when signature is supplied).

    Fail-closed on incomplete envelopes (review finding: empty-string v1
    fields silently produce ambiguous security claims):
    - trust_root_version, build_digest and snapshot_digest are ALWAYS
      required (ValueError otherwise) - they are known before signing.
    - signature and signer_key_id must be empty TOGETHER (unsigned build)
      or nonempty TOGETHER (signed build); half-signed is refused.
    """
    for name, value in (
        ("trust_root_version", trust_root_version),
        ("build_digest", build_digest),
        ("snapshot_digest", snapshot_digest),
    ):
        if not _nonempty(value):
            raise ValueError("v1_receipt_field_required:" + name)
    if _nonempty(signature) != _nonempty(signer_key_id):
        raise ValueError("v1_receipt_half_signed")
    return AdmissibilityReceiptV1(
        schema=RECEIPT_SCHEMA_V1,
        operation=operation,
        event_id=(
            "evt_"
            + hashlib.sha256(
                (
                    memory_id + request_digest + decision + snapshot_digest
                ).encode("utf-8")
            ).hexdigest()[:24]
        ),
        memory_id=memory_id,
        ts=utc_now_iso(),
        operator_subject=operator_subject,
        tenant=tenant,
        request_digest=request_digest,
        canonicalization=CANONICALIZATION,
        gate="yuyay-13",
        decision=decision,
        astype_signature=signature,
        status_current=status_current,
        trust_root_version=trust_root_version,
        build_digest=build_digest,
        signer_key_id=signer_key_id,
        snapshot_digest=snapshot_digest,
    )


def signed_payload(receipt: AdmissibilityReceiptV1) -> str:
    """Domain-separated canonical payload covering the FULL v1 envelope.

    Covers every field except the signature itself: schema, operation,
    event_id, memory_id, ts, operator, tenant, request_digest,
    canonicalization, gate, decision, status, trust_root_version,
    build_digest, signer_key_id and snapshot_digest. Post-commit edits
    to any of these change the payload, so a verifiable signature over
    this payload detects tampering even before DSSE lands (ROADMAP).
    """
    d = receipt.to_dict()
    d.pop("signature", None)
    d.pop("astype_signature", None)
    body = json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return SIGNED_PAYLOAD_DOMAIN + "\u0000" + body
