"""Memory Court: adjudicated, append-only agent memory with fail-closed admission.

Day-3 implementation slice of the Memory Court program
(docs/memory-court/MEMORY_COURT_DAY1.md / MEMORY_COURT_DAY2.md).
Labels: the gateway here is MEASURED by its own tests; end-to-end DSSE
_signing against the owner trust root remains ROADMAP (requires key
material that is owner-gated). Signers and Khipu writers are injected
adapters so the fail-closed contract itself can be verified without
production key material.
"""

from .gateway import MemoryCourtGateway, Outcome, Request, SignerKeyUnknown, SignerUnavailable
from .khipu_writer import FileKhipuWriter, KhipuWriteError

__all__ = [
    "MemoryCourtGateway",
    "Outcome",
    "Request",
    "SignerKeyUnknown",
    "SignerUnavailable",
    "FileKhipuWriter",
    "KhipuWriteError",
]
