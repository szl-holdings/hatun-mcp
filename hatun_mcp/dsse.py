"""
hatun_mcp.dsse — receipt minting, Khipu DAG append, and BLS aggregate signatures.

This module is the receipt/signature surface that the organ adapters and the
quorum engine call. It builds on the REAL primitives already shipped in
hatun_mcp.governance (the append-only sha256 Khipu chain and the ECDSA-P256 DSSE
signer) and adds:

  * mint_receipt(...)          -> append one receipt to the Khipu DAG, return hash.
  * BlsAggregator              -> aggregate N organ receipts (one MCP call that
                                  fans out to N organs) into a single signature.

BLS aggregation:
  * Primary: BLS12-381 via `py_ecc.bls.G2ProofOfPossession` (the IETF
    draft-irtf-cfrg-bls-signature scheme used by Ethereum). Sign / Aggregate /
    AggregateVerify are REAL curve operations over the N receipt-hash messages.
  * Fallback (py_ecc not installed in the runtime): an HONEST 'MERKLE-AGG' mode
    that binds the N receipt hashes into one deterministic sha256 Merkle root and
    labels the envelope clearly (honest disclosure). A BLS signature is never faked.

SPDX-License-Identifier: Apache-2.0
Author: Yachay (CTO authority) · Built by Perplexity Computer Agent · 2026-06-03
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .governance import DsseSigner, KhipuChain, KhipuReceipt

# ── Optional real BLS backend (BLS12-381) ───────────────────────────────────────
try:
    from py_ecc.bls import G2ProofOfPossession as _BLS  # type: ignore
    _HAS_BLS = True
except Exception:  # pragma: no cover - py_ecc optional in the slim image
    _BLS = None
    _HAS_BLS = False


def mint_receipt(
    chain: KhipuChain,
    signer: Optional[DsseSigner],
    *,
    tool: str,
    client_id: str,
    operation_id: str,
    status: str,
    tripwire: Optional[str] = None,
    yuyay_min_axis: Optional[float] = None,
    hatun_mcp_factor: float = 0.0,
    puriq_score: float = 0.0,
    detail: Optional[dict] = None,
) -> KhipuReceipt:
    """Append one receipt to the Khipu DAG and return it (carries continuum_hash)."""
    return chain.emit(
        tool=tool, client_id=client_id, operation_id=operation_id, status=status,
        tripwire=tripwire, yuyay_min_axis=yuyay_min_axis,
        hatun_mcp_factor=hatun_mcp_factor, puriq_score=puriq_score,
        detail=detail or {}, signer=signer,
    )


def _merkle_root(hashes: list[str]) -> str:
    """Deterministic binary sha256 Merkle root over the ordered receipt hashes."""
    if not hashes:
        return "0" * 64
    layer = [bytes.fromhex(h) if len(h) == 64 else hashlib.sha256(h.encode()).digest()
             for h in hashes]
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer), 2):
            a = layer[i]
            b = layer[i + 1] if i + 1 < len(layer) else layer[i]
            nxt.append(hashlib.sha256(a + b).digest())
        layer = nxt
    return layer[0].hex()


@dataclass
class AggregateResult:
    mode: str                       # "BLS12-381" | "MERKLE-AGG"
    n_organs: int
    receipt_hashes: list[str]
    aggregate: str                  # hex signature (BLS) or merkle root (fallback)
    merkle_root: str
    note: str = ""
    organs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "n_organs": self.n_organs,
            "organs": self.organs,
            "receipt_hashes": self.receipt_hashes,
            "aggregate_signature": self.aggregate,
            "merkle_root": self.merkle_root,
            "note": self.note,
        }


class BlsAggregator:
    """Aggregate the receipts of N organs that participated in one MCP call.

    Each organ is assigned a deterministic BLS keypair derived from its name and
    an optional per-process seed (env HATUN_MCP_BLS_SEED). For an MCP call that
    fanned out to organs [o1..oN], each organ signs its own receipt hash; the N
    signatures aggregate into a single BLS signature verifiable against the N
    public keys + N messages (AggregateVerify).
    """

    def __init__(self, seed: Optional[str] = None) -> None:
        self.seed = seed or os.environ.get("HATUN_MCP_BLS_SEED", "hatun-mcp-doctrine-v11")
        self._sk: dict[str, int] = {}
        self._pk: dict[str, bytes] = {}

    @property
    def available(self) -> bool:
        return _HAS_BLS

    def _keypair(self, organ: str):
        if organ not in self._sk:
            ikm = hashlib.sha256(f"{self.seed}:{organ}".encode()).digest()
            sk = _BLS.KeyGen(ikm)
            self._sk[organ] = sk
            self._pk[organ] = _BLS.SkToPk(sk)
        return self._sk[organ], self._pk[organ]

    def public_key(self, organ: str) -> Optional[str]:
        if not _HAS_BLS:
            return None
        _, pk = self._keypair(organ)
        return pk.hex()

    def aggregate(self, organ_receipts: list[tuple[str, str]]) -> AggregateResult:
        """organ_receipts = [(organ_name, receipt_continuum_hash), ...].

        Returns an AggregateResult. With >= 1 receipt and a real BLS backend this
        is a genuine BLS12-381 aggregate signature; otherwise an honest Merkle-root
        binding (labeled MERKLE-AGG).
        """
        organs = [o for o, _ in organ_receipts]
        hashes = [h for _, h in organ_receipts]
        merkle = _merkle_root(hashes)

        if _HAS_BLS and organ_receipts:
            sigs = []
            for organ, rhash in organ_receipts:
                sk, _ = self._keypair(organ)
                msg = bytes.fromhex(rhash) if len(rhash) == 64 else rhash.encode()
                sigs.append(_BLS.Sign(sk, msg))
            agg = _BLS.Aggregate(sigs)
            return AggregateResult(
                mode="BLS12-381", n_organs=len(organ_receipts), receipt_hashes=hashes,
                aggregate=agg.hex(), merkle_root=merkle, organs=organs,
                note=("REAL BLS12-381 aggregate over the N organ receipt hashes "
                      "(py_ecc G2ProofOfPossession). Verify with AggregateVerify "
                      "against the N organ public keys + their receipt hashes."),
            )

        return AggregateResult(
            mode="MERKLE-AGG", n_organs=len(organ_receipts), receipt_hashes=hashes,
            aggregate=merkle, merkle_root=merkle, organs=organs,
            note=("BLS backend (py_ecc) not available in this runtime; aggregation "
                  "falls back to a deterministic sha256 Merkle root binding the N "
                  "receipt hashes. Honest PLACEHOLDER — disclosed, NOT a fake BLS sig. "
                  "Install py_ecc to enable real BLS12-381 aggregation."),
        )

    def verify(self, organ_receipts: list[tuple[str, str]], aggregate_hex: str) -> bool:
        """Verify a real BLS aggregate (no-op verify for the Merkle fallback,
        which is checked by recomputing the root)."""
        if not _HAS_BLS:
            return _merkle_root([h for _, h in organ_receipts]) == aggregate_hex
        pks, msgs = [], []
        for organ, rhash in organ_receipts:
            _, pk = self._keypair(organ)
            pks.append(pk)
            msgs.append(bytes.fromhex(rhash) if len(rhash) == 64 else rhash.encode())
        try:
            return _BLS.AggregateVerify(pks, msgs, bytes.fromhex(aggregate_hex))
        except Exception:
            return False
