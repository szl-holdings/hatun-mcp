"""Memory Court: adjudicated, append-only agent memory with fail-closed admission.

Day-4 trust-root slice of the Memory Court program
(docs/memory-court/MEMORY_COURT_DAY1.md .. MEMORY_COURT_DAY4.md),
hardened after the two-brain adversarial design review (GPT-6 via the
ChatGPT desktop app + mistral-large-4:cloud, 2026-11-20, both verdicts
FIX-FIRST; findings folded in before implementation).
Labels: the gateway is MEASURED by its own contract tests; real DSSE
signing against the owner trust root remains ROADMAP (requires key
material that is owner-gated). Signers, verifiers, trust-root providers
and Khipu writers are injected adapters so the fail-closed contract
itself is verified without production key material.
"""

from .gateway import MemoryCourtGateway, Outcome, Request, SignerKeyUnknown, SignerUnavailable
from .khipu_writer import FileKhipuWriter, KhipuPreconditionError, KhipuWriteError
from .receipts import (
    RECEIPT_SCHEMA,
    RECEIPT_SCHEMA_V1,
    AdmissibilityReceipt,
    AdmissibilityReceiptV1,
    build_receipt,
    build_receipt_v1,
    canonical_sha256,
    signed_payload,
)
from .trust_root import StaticTrustRoot, TrustRootError, TrustSnapshot

__all__ = [
    "MemoryCourtGateway",
    "Outcome",
    "Request",
    "SignerKeyUnknown",
    "SignerUnavailable",
    "FileKhipuWriter",
    "KhipuWriteError",
    "KhipuPreconditionError",
    "AdmissibilityReceipt",
    "AdmissibilityReceiptV1",
    "TrustSnapshot",
    "TrustRootError",
    "StaticTrustRoot",
    "build_receipt",
    "build_receipt_v1",
    "signed_payload",
    "canonical_sha256",
    "RECEIPT_SCHEMA",
    "RECEIPT_SCHEMA_V1",
]
