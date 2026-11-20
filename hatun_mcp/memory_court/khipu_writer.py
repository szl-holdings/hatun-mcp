"""Khipu writer adapter (append-only truth log boundary).

The production substrate is szl-khipu LMDB (agentic database ruling,
session-10): append-only; revocation appends; nothing is ever deleted.
This slice ships an explicit adapter BOUNDARY plus a simple JSONL
file-backed implementation with an injectable failure mode so the
fail-closed contract (khipu write failure => 503, never success) is
testable. The LMDB adapter is ROADMAP until it lands in szl-khipu.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional

from .receipts import AdmissibilityReceipt

__all__ = ["KhipuWriteError", "FileKhipuWriter"]


class KhipuWriteError(Exception):
    """The append failed; nothing was committed."""


class FileKhipuWriter:
    """Append-only JSONL store: idempotency_key -> committed receipt.

    Single-writer, single-process (test scope). Production multi-writer
    and replication behavior is szl-khipu's contract, not this adapter's.
    Each append is flushed; an append that raises leaves the store
    unchanged (the caller treats that as commit_outcome_unknown).
    """

    def __init__(self, path: str, *, fail_injected: bool = False) -> None:
        self._path = path
        self._fail_injected = fail_injected
        self._entries: Dict[str, AdmissibilityReceipt] = {}
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
                receipt = AdmissibilityReceipt(**_remap(record))
                self._entries[key] = receipt

    def get(self, key: str) -> Optional[AdmissibilityReceipt]:
        return self._entries.get(key)

    def append(self, key: str, receipt: AdmissibilityReceipt) -> None:
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


def _remap(record: dict) -> dict:
    # receipt.to_dict() renames astype_signature -> signature on read-back
    if "signature" in record:
        record["astype_signature"] = record.pop("signature")
    return record
