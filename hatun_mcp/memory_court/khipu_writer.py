"""Khipu writer adapter (append-only truth log boundary).

Day-4: TOCTOU closure, hardened after the two-brain adversarial review
(GPT-6 via the ChatGPT app + mistral-large-4:cloud, 2026-11-20, both
verdicts FIX-FIRST):

- `append_with_precondition` re-asserts the CURRENT trust-root snapshot
  digest INSIDE the same lock that performs the duplicate check + write +
  flush + fsync. Rotation between sign and commit therefore cannot slip
  an admission past a stale snapshot (CRITICAL finding: trust-root
  rotation must be transactionally bound to the append).
- v0 receipts can no longer be appended: schema discrimination refuses
  a v0 write (HIGH finding: never write new v0 receipts). Legacy v0 lines
  in the file remain LOADABLE for audit (read-only; the gateway refuses
  to replay them).
- Appends remain single-writer, flushed and fsynced per line; an append
  that raises leaves the store unchanged (commit outcome unknown is the
  caller's failure, never success).

The production substrate remains szl-khipu LMDB (agentic database ruling,
session-10): append-only; revocation appends; nothing is ever deleted.
The LMDB adapter keeps its precondition INSIDE the write transaction
when it lands (ROADMAP; the JSONL lock here is the boundary contract).
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict, Optional

from .receipts import (
    RECEIPT_SCHEMA,
    RECEIPT_SCHEMA_V1,
    AdmissibilityReceipt,
    AdmissibilityReceiptV1,
)

__all__ = ["KhipuWriteError", "KhipuPreconditionError", "FileKhipuWriter"]


class KhipuWriteError(Exception):
    """The append failed; nothing was committed."""


class KhipuPreconditionError(KhipuWriteError):
    """The trust root moved (or could not be re-read) in the commit
    boundary; nothing was written."""


def _remap(record: dict) -> dict:
    # to_dict() renames astype_signature -> signature on read-back
    if "signature" in record:
        record["astype_signature"] = record.pop("signature")
    return record


def _rehydrate(record: dict):
    """Schema discrimination on load: v1 receipts stay v1; v0 stays v0
    (read-only legacy). Unknown schemas refuse to load at all: an
    undecidable record is not a receipt (unknown stays UNKNOWN)."""
    schema = record.get("schema", "")
    if schema == RECEIPT_SCHEMA_V1:
        return AdmissibilityReceiptV1(**_remap(record))
    if schema == RECEIPT_SCHEMA:
        return AdmissibilityReceipt(**_remap(record))
    raise ValueError("unknown_receipt_schema:" + str(schema))


class FileKhipuWriter:
    """Append-only JSONL store: idempotency_key -> committed receipt.

    Single-process, single-writer (lock held across re-assert + write +
    flush + fsync). Production multi-writer/replication behavior stays
    szl-khipu's contract, not this adapter's.
    """

    def __init__(self, path: str, *, fail_injected: bool = False) -> None:
        self._path = path
        self._fail_injected = fail_injected
        self._lock = threading.Lock()
        self._entries: Dict[str, object] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        with open(self._path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                key = record.pop("idempotency_key")
                self._entries[key] = _rehydrate(record)

    def get(self, key: str):
        return self._entries.get(key)

    # -- raw append (day-3 surface, now v1-only) --------------------------

    def append(self, key: str, receipt) -> None:
        """Append a v1 receipt. v0 appends are LOCKED (never write new v0)."""
        if not isinstance(receipt, AdmissibilityReceiptV1):
            raise KhipuWriteError("v0_append_locked: legacy receipts are read-only")
        with self._lock:
            self._append_locked(key, receipt)

    def append_with_precondition(
        self,
        key: str,
        receipt,
        *,
        expect_snapshot_digest: str,
        current_snapshot_digest,
    ) -> None:
        """TOCTOU-closed append (day-4).

        `current_snapshot_digest` is a callable re-asserted INSIDE the
        commit lock; its failure or divergence from the digest the
        gateway captured at invoke start aborts the append with
        KhipuPreconditionError and leaves the store unchanged.
        """
        if not isinstance(receipt, AdmissibilityReceiptV1):
            raise KhipuWriteError("v0_append_locked: legacy receipts are read-only")
        with self._lock:
            if self._fail_injected:
                raise KhipuWriteError("injected failure: nothing committed")
            try:
                live = current_snapshot_digest()
            except Exception:
                # Provider died inside the commit boundary: unknown state
                # is a refusal, never a best-effort commit.
                raise KhipuPreconditionError("trust_root_unreadable_in_commit")
            if not isinstance(live, str) or not live.strip():
                raise KhipuPreconditionError("trust_root_digest_invalid")
            if live != expect_snapshot_digest:
                raise KhipuPreconditionError("trust_root_rotated")
            self._append_locked(key, receipt)

    def _append_locked(self, key: str, receipt: AdmissibilityReceiptV1) -> None:
        # caller holds the lock
        if self._fail_injected:
            raise KhipuWriteError("injected failure: nothing committed")
        if key in self._entries:
            raise KhipuWriteError("duplicate append: replay via get() instead")
        record = receipt.to_dict()
        record["idempotency_key"] = key
        with open(self._path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._entries[key] = receipt
