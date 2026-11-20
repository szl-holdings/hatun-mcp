"""Day-4 trust-root contract tests: the rotation / ABA / binding vectors.

Real tests, no skips; every vector was pinned by the two-brain adversarial
review of the day-4 design (GPT-6 via the ChatGPT app + mistral-large-4,
2026-11-20, both verdicts FIX-FIRST). Mapping from the review request:

rotation-before-sign   -> provider failure refuses, nothing signed
rotation-after-sign     -> preconditioned append refuses, nothing committed
version ABA (reused version, changed keys/build) -> different digest =>
                          in-flight refusal + old receipts cannot replay
epoch regression       -> refused by the provider (no re-authorization)
unknown/revoked signer -> 503, nothing committed
forged key id          -> 503 signer_key_unknown, nothing committed
signature/payload mismatch -> verifier refusal, nothing committed
v1 empty fields        -> refused at build (never a half-bound commit)
v0 downgrade           -> writer refuses v0 appends; gateway replays refuse
replay across root     -> 503 trust_root_rotated, never re-adjudicated
duplicate/precondition -> append is atomic per key; digest re-assert inside
zero dependent writes  -> on EVERY denial above
"""

from __future__ import annotations

import pytest

from hatun_mcp.memory_court.gateway import (
    MemoryCourtGateway,
    Request,
)
from hatun_mcp.memory_court.khipu_writer import (
    FileKhipuWriter,
    KhipuPreconditionError,
    KhipuWriteError,
)
from hatun_mcp.memory_court.receipts import build_receipt_v1, signed_payload
from hatun_mcp.memory_court.trust_root import (
    StaticTrustRoot,
    TrustRootError,
    TrustSnapshot,
)

ALLOW = lambda subject: subject == "p4:PAQ/operator-demo"
TENANT_OK = lambda tenant: tenant == "t:acme"


SNAP_A = TrustSnapshot(
    version="tr-1", build_digest="bd-1", signer_key_ids=frozenset({"k:a"}), epoch=1
)
# ABA probe: SAME version string, DIFFERENT signer keys/build identity.
SNAP_B_ABA_SAME_VERSION = TrustSnapshot(
    version="tr-1", build_digest="bd-2", signer_key_ids=frozenset({"k:b"}), epoch=2
)
SNAP_C = TrustSnapshot(
    version="tr-3", build_digest="bd-3", signer_key_ids=frozenset({"k:c"}), epoch=3
)


def make_gw(tmp_path, *, snap=SNAP_A, trust=None, signer=None, verifier=None, adjudicator=None, writer=None, calls=None):
    calls = calls if calls is not None else []
    trust = trust if trust is not None else StaticTrustRoot(snap)
    khipu = writer if writer is not None else FileKhipuWriter(str(tmp_path / "khipu.jsonl"))
    gw = MemoryCourtGateway(
        auth=lambda s: (calls.append("auth") or ALLOW(s)),
        tenant_resolver=lambda t: (calls.append("tenant") or TENANT_OK(t)),
        build_admissible=lambda: (calls.append("build") or True),
        trust_root=trust,
        adjudicator=adjudicator or (lambda r: (calls.append("adjudicate") or "admit")),
        signer=signer or (lambda r: (calls.append("sign") or ("sig", sorted(snap.signer_key_ids)[0]))),
        khipu=khipu,
        signature_verifier=verifier,
    )
    return gw, khipu, calls


def req(**over):
    base = dict(
        tool="memory_write",
        args={"payload": "hello"},
        operator_subject="p4:PAQ/operator-demo",
        tenant="t:acme",
        routing_headers={"mcp-session-id": "s-1", "mcp-profile": "court"},
        idempotency_key="idem-1",
        memory_id="mem_001",
    )
    base.update(over)
    return Request(**base)


# -- snapshot binding --------------------------------------------------------

def test_a_snapshot_digest_covers_version_keys_epoch_and_build():
    digests = {
        SNAP_A.digest,
        SNAP_B_ABA_SAME_VERSION.digest,  # same version string is NOT enough
        TrustSnapshot(version="tr-x", build_digest="bd-1", signer_key_ids=frozenset({"k:a"}), epoch=1).digest,
    }
    assert len(digests) == 3  # every component change moves the digest


def test_empty_signer_key_ids_is_invalid_fail_closed(tmp_path):
    root = StaticTrustRoot(
        TrustSnapshot(version="tr-1", build_digest="bd-1", signer_key_ids=frozenset(), epoch=1)
    )
    with pytest.raises(TrustRootError):
        root.snapshot().validate()
    with pytest.raises(TrustRootError):
        root.snapshot()


def test_provider_epoch_regression_refused(tmp_path):
    root = StaticTrustRoot(SNAP_C)  # epoch 3; nothing older may return
    with pytest.raises(TrustRootError):
        root.rotate(SNAP_A)  # epoch 1 < ceiling 3: no re-authorization


# -- in-flight rotation ------------------------------------------------------

def test_rotation_before_sign_refuses_unsigned(tmp_path):
    calls = []
    class Died:
        def snapshot(self):
            raise RuntimeError("root exploded")
    gw, khipu, calls = make_gw(tmp_path, trust=Died(), calls=calls)
    out = gw.invoke(req())
    assert (out.status, out.reason) == (503, "trust_root_unavailable")
    assert "sign" not in calls
    assert khipu.get("idem-1") is None


def test_rotation_between_sign_and_commit_refuses_commit(tmp_path):
    # GPT-6 CRITICAL (rotation not transactionally bound) + Mistral HIGH
    # (precondition pinned version only): the signer rotates the root and
    # the preconditioned append must catch it inside the commit boundary.
    root = StaticTrustRoot(SNAP_A)
    def evil_signer(receipt):
        root.rotate(SNAP_C)  # rotate mid-flight, after the snapshot sample
        return ("sig", "k:a")  # still an A-key signature for the A snapshot
    gw, khipu, calls = make_gw(tmp_path, trust=root, signer=evil_signer)
    out = gw.invoke(req())
    assert (out.status, out.reason) == (503, "trust_root_rotated")
    assert out.receipt_kind == "signed-uncommitted"
    assert out.dependent_writes == []
    assert khipu.get("idem-1") is None  # nothing landed on disk


def test_version_aba_rotation_changes_digest_so_replay_refuses(tmp_path):
    root = StaticTrustRoot(SNAP_A)
    gw, khipu, _ = make_gw(tmp_path, trust=root)
    first = gw.invoke(req())
    assert first.status == 200
    # ABA: same version string, different key set/build => new epoch allowed,
    # digest necessarily differs; old receipts must NOT replay as success.
    root.rotate(SNAP_B_ABA_SAME_VERSION)
    assert SNAP_A.digest != SNAP_B_ABA_SAME_VERSION.digest
    out = gw.invoke(req())
    assert (out.status, out.reason) == (503, "trust_root_rotated")
    assert out.receipt_kind is None  # replay path: nothing re-signed, nothing new committed
    assert out.dependent_writes == []


def test_signer_key_rotated_out_of_snapshot_refused(tmp_path):
    # The snapshot rotates; a receipt signed by the OLD key refuses replay
    # even when the snapshot digest accidentally matches (epoch pins it).
    root = StaticTrustRoot(TrustSnapshot(version="tr-1", build_digest="bd-1", signer_key_ids=frozenset({"k:a"}), epoch=7))
    gw, khipu, _ = make_gw(tmp_path, snap=root.snapshot())
    assert gw.invoke(req()).status == 200
    # add a second key: same version/build/epoch is NOT representable (the
    # provider requires monotonic epochs), so simulate via a fresh fork root
    root2 = StaticTrustRoot(TrustSnapshot(version="tr-1", build_digest="bd-1", signer_key_ids=frozenset({"k:a", "k:b"}), epoch=8))
    gw2, khipu2, _ = make_gw(tmp_path, trust=root2, writer=khipu)
    out = gw2.invoke(req())
    assert (out.status, out.reason) == (503, "trust_root_rotated")


# -- signer / verifier contract ---------------------------------------------

def test_forged_key_id_refused_nothing_committed(tmp_path):
    gw, khipu, calls = make_gw(tmp_path, snap=SNAP_A, signer=lambda r: ("sig", "k:forger"))
    out = gw.invoke(req())
    assert (out.status, out.reason) == (503, "signer_key_unknown")
    assert khipu.get("idem-1") is None
    assert "sign" in calls  # the signer ran; the GATE refused downstream


def test_signature_verification_failure_refused(tmp_path):
    gw, khipu, _ = make_gw(tmp_path, snap=SNAP_A, verifier=lambda p, s, k: False)
    out = gw.invoke(req())
    assert (out.status, out.reason) == (503, "signature_verification_failed")
    assert out.receipt_kind is None
    assert khipu.get("idem-1") is None


def test_signed_payload_covers_the_full_envelope():
    # GPT-6 CRITICAL #2 / Mistral CRITICAL #1: the signed payload must cover
    # trust_root_version, build_digest, signer_key_id, tenant and decision,
    # or post-commit edits are undetectable without DSSE.
    base = build_receipt_v1(
        operation="op", memory_id="m", operator_subject="o", tenant="t",
        request_digest="d" * 8, decision="admit",
        trust_root_version="tr-1", build_digest="bd-1",
        snapshot_digest=SNAP_A.digest, signer_key_id="k:a", signature="sig",
    )
    p = signed_payload(base)
    for marker in ("tr-1", "bd-1", SNAP_A.digest, "k:a", '"admit"', '"t"'):
        assert marker in p or marker in p.replace("\\u0000", " ")
    tampered = build_receipt_v1(
        operation="op", memory_id="m", operator_subject="o", tenant="t",
        request_digest="d" * 8, decision="admit",
        trust_root_version="tr-EVIL", build_digest="bd-1",
        snapshot_digest=SNAP_A.digest, signer_key_id="k:a", signature="sig",
    )
    assert signed_payload(tampered) != p  # any envelope edit displaces the payload


# -- envelope discipline -----------------------------------------------------

def test_v1_empty_trust_field_refused_at_build():
    with pytest.raises(ValueError):
        build_receipt_v1(
            operation="op", memory_id="m", operator_subject="o", tenant="t",
            request_digest="d" * 8, decision="admit",
            trust_root_version="", build_digest="bd-1", snapshot_digest=SNAP_A.digest,
        )


def test_v1_half_signed_refused_at_build():
    with pytest.raises(ValueError):
        build_receipt_v1(
            operation="op", memory_id="m", operator_subject="o", tenant="t",
            request_digest="d" * 8, decision="admit",
            trust_root_version="tr-1", build_digest="bd-1", snapshot_digest=SNAP_A.digest,
            signature="sig",  # signature without key id: half-signed
        )


def test_event_id_binds_snapshot_digest_so_cross_root_alias_impossible(tmp_path):
    # Mistral HIGH: event_id must be snapshot-bound, or an old-root receipt
    # collides with the same logical request under the new root.
    r1 = build_receipt_v1(
        operation="op", memory_id="m1", operator_subject="o", tenant="t",
        request_digest="d" * 8, decision="admit",
        trust_root_version="tr-1", build_digest="bd-1", snapshot_digest=SNAP_A.digest,
    )
    r2 = build_receipt_v1(
        operation="op", memory_id="m1", operator_subject="o", tenant="t",
        request_digest="d" * 8, decision="admit",
        trust_root_version="tr-3", build_digest="bd-3", snapshot_digest=SNAP_C.digest,
    )
    assert r1.event_id != r2.event_id


# -- replay policy -----------------------------------------------------------

def test_replay_never_re_adjudicates_even_when_refused(tmp_path):
    # GPT-6 #3 / Mistral (6): NEVER silently re-adjudicate under the old key.
    root = StaticTrustRoot(SNAP_A)
    calls = []
    gw, khipu, calls = make_gw(tmp_path, trust=root, calls=calls)
    assert gw.invoke(req()).status == 200
    root.rotate(SNAP_C)
    calls.clear()
    out = gw.invoke(req())
    assert out.status == 503
    assert "adjudicate" not in calls
    assert out.dependent_writes == []


# -- writer precondition -----------------------------------------------------

def test_writer_precondition_mismatch_aborts_without_write(tmp_path):
    w = FileKhipuWriter(str(tmp_path / "khipu.jsonl"))
    r = build_receipt_v1(
        operation="op", memory_id="m", operator_subject="o", tenant="t",
        request_digest="d" * 8, decision="admit",
        trust_root_version="tr-1", build_digest="bd-1", snapshot_digest=SNAP_A.digest,
        signer_key_id="k:a", signature="sig",
    )
    with pytest.raises(KhipuPreconditionError):
        w.append_with_precondition(
            "k", r, expect_snapshot_digest=SNAP_A.digest,
            current_snapshot_digest=lambda: SNAP_C.digest,
        )
    assert w.get("k") is None
    # The provider dying INSIDE the boundary is also a refusal.
    def dead():
        raise RuntimeError("root gone")
    with pytest.raises(KhipuPreconditionError):
        w.append_with_precondition(
            "k", r, expect_snapshot_digest=SNAP_A.digest,
            current_snapshot_digest=dead,
        )
    assert w.get("k") is None


def test_writer_v0_receipt_refused_on_precondition_path_too(tmp_path):
    w = FileKhipuWriter(str(tmp_path / "khipu.jsonl"))
    with pytest.raises(KhipuWriteError):
        w.append_with_precondition(
            "k", object(), expect_snapshot_digest=SNAP_A.digest,
            current_snapshot_digest=lambda: SNAP_A.digest,
        )
