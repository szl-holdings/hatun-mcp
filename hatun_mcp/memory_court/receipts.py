"""Admissibility receipt construction and canonical digests.

Canonicalization note: this slice uses deterministic stdlib JSON
(sort_keys, compact separators, ensure_ascii=False) as a documented
simplification of JCS (RFC 8785). Full JCS is a day-4+ task; the digest
field name records which form was used. No number or receipt is ever
fabricated here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict

RECEIPT_SCHEMA = "szl.memory-admissibility-receipt/v0"
CANONICALIZATION = "stdlib-json-sortkeys-v1"


def canonical_sha256(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AdmissibilityReceipt:
    """Atomic record per MEMORY_COURT_DAY1.md (v0 subset).

    The full v0 envelope includes source/build/doctrine digests and the
    DSSE block; those fields land with the trust-root work and remain
    ROADMAP until then. This subset is sufficient for the fail-closed
    gate contract tests; nothing here overclaims.
    """

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
