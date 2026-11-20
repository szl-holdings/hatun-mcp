"""Day-3+4 gateway contract tests: the fail-closed decision table.

Real tests, no skips. Every vector asserts the full triple:
(status, receipt_kind, dependent_writes) plus the invariant that
infrastructure was never touched on a failed gate.

Hardened table after the day-3 adversarial review (mistral-large-4 +
qwen, both FIX-FIRST) and re-based on the day-4 trust-bound gateway
(GPT-6 + mistral-large-4 day-4 design review, both FIX-FIRST):
  unauthenticated    -> 401, no receipt
  wrong tenant       -> 403, no receipt
  malformed routing  -> 400
  empty memory_id    -> 400 memory_id_required
  missing/blank idem key -> 503 idempotency_key_required (no commit-less claim)
  dirty/unknown build -> 503
  trust root unknown/invalid -> 503, nothing sampled further
  trust root unavailable (crash) -> 503
  signer key unknown (raise or forged key id) -> 503
  signer unavailable  -> 503
  generic signer error -> 503 signer_error
  empty signature     -> 503 signer_invalid_signature, nothing committed
  adjudication block   -> 503
  adjudication unknown -> 503 (unknown stays UNKNOWN)
  khipu write failure  -> 503 signed-uncommitted, never success
  abstain             -> 200 abstention, committed, no dependent writes
  admit               -> 200 admission, dependent write released
  replay (same request) -> original receipt, no re-sign, no re-adjudicate,
                          admission re-releases its write
  replay (different request, same key) -> 409 idempotency_conflict
Day-4 trust bindings (see test_trust_root_day4.py for the rotation
vectors): every committed receipt carries nonempty trust_root_version,
build_digest, signer_key_id and snapshot_digest; v0 is read-only legacy.
"""

from __future__ import annotations

import json

import pytest

from hatun_mcp.memory_court.gateway import (
    MemoryCourtGateway,
    Request,
    SignerKeyUnknown,
    SignerUnavailable,
)
from hatun_mcp.memory_court.khipu_writer import FileKhipuWriter, KhipuWriteError
from hatun_mcp.memory_court.receipts import (
    RECEIPT_SCHEMA,
    build_receipt,
    build_receipt_v1,
)
from hatun_mcp.memory_court.trust_root import (
    StaticTrustRoot,
    TrustRootError,
    TrustSnapshot,
)


ALLOW = lambda subject: subject == "p4:PAQ/operator-demo"
TENANT_OK = lambda tenant: tenant == "t:acme"

TRUST_SNAP = TrustSnapshot(
    version="tr-2026-11-20",
    build_digest="bd-hatun-mcp",
    signer_key_ids=frozenset({"k:yuyay-13"}),
    epoch=1,
)
SNAP_DIGEST = TRUST_SNAP.digest


class BrokenTrustRoot:
    kind = "generic"

    def snapshot(self):
        if self.kind == "generic":
            raise RuntimeError("provider offline")
        raise TrustRootError("trust_root_invalid")


def sign_ok(receipt):
    return "k=szl-yuyay-13;sig=test", "k:yuyay-13"


class Stubs:
    def __init__(self, tmp_path, *, adjudicator=None, writer=None, trust_root=None):
        self.calls = []
        self.trust = trust_root if trust_root is not None else StaticTrustRoot(TRUST_SNAP)
        self.khipu = writer if writer is not None else FileKhipuWriter(str(tmp_path / "khipu.jsonl"))
        self.gw = MemoryCourtGateway(
            auth=lambda s: (self.calls.append("auth") or ALLOW(s)),
            tenant_resolver=lambda t: (self.calls.append("tenant") or TENANT_OK(t)),
            build_admissible=lambda: (self.calls.append("build") or True),
            trust_root=self.trust,
            adjudicator=adjudicator or (lambda r: (self.calls.append("adjudicate") or "admit")),
            signer=lambda r: (self.calls.append("sign") or sign_ok(r)),
            khipu=self.khipu,
        )
        self.commit_calls = []
        real_commit = self.khipu.append_with_precondition

        def commit(key, receipt, **kwargs):
            self.commit_calls.append(key)
            return real_commit(key, receipt, **kwargs)

        self.khipu.append_with_precondition = commit


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


# -- refusals ---------------------------------------------------------------

def test_unauthenticated_caller(tmp_path):
    s = Stubs(tmp_path)
    s.gw._auth = lambda subj: False
    out = s.gw.invoke(req(operator_subject="intruder"))
    assert (out.status, out.reason) == (401, "operator_auth_failed")
    assert out.receipt_kind is None
    assert out.dependent_writes == []
    assert s.commit_calls == []


def test_wrong_tenant(tmp_path):
    s = Stubs(tmp_path)
    s.gw._tenants = lambda t: False
    out = s.gw.invoke(req(tenant="t:evil"))
    assert (out.status, out.reason) == (403, "tenant_mismatch")
    assert out.receipt_kind is None
    assert s.commit_calls == []


def test_malformed_routing_headers_missing_session(tmp_path):
    s = Stubs(tmp_path)
    out = s.gw.invoke(req(routing_headers={"mcp-profile": "court"}))
    assert (out.status, out.reason) == (400, "malformed_routing_headers")
    assert out.receipt_kind is None


def test_malformed_routing_headers_blank_profile(tmp_path):
    s = Stubs(tmp_path)
    out = s.gw.invoke(req(routing_headers={"mcp-session-id": "s-1", "mcp-profile": "  "}))
    assert out.status == 400


def test_memory_id_required(tmp_path):
    s = Stubs(tmp_path)
    out = s.gw.invoke(req(memory_id=""))
    assert (out.status, out.reason) == (400, "memory_id_required")
    assert out.receipt_kind is None
    assert s.commit_calls == []


def test_missing_idempotency_key_refused(tmp_path):
    # Review finding CRITICAL: admit with no commit anchor was a LEAK.
    # Now: no idempotency key -> no commit path at all.
    s = Stubs(tmp_path)
    out = s.gw.invoke(req(idempotency_key=None))
    assert (out.status, out.reason) == (503, "idempotency_key_required")
    assert out.receipt_kind is None
    assert out.committed_receipt is None
    assert out.dependent_writes == []
    assert s.commit_calls == []
    # Recovery rule preserved: a fresh writer sees no fabricated entries.
    w2 = FileKhipuWriter(str(tmp_path / "khipu.jsonl"))
    assert w2.get("idem-1") is None


def test_blank_idempotency_key_refused(tmp_path):
    s = Stubs(tmp_path)
    out = s.gw.invoke(req(idempotency_key="   "))
    assert (out.status, out.reason) == (503, "idempotency_key_required")
    assert s.commit_calls == []


def test_dirty_or_unknown_build(tmp_path):
    s = Stubs(tmp_path)
    s.gw._build_ok = lambda: False
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "build_not_admissible")
    assert out.receipt_kind is None
    assert s.commit_calls == []


def test_trust_root_invalid_refuses_before_anything_else(tmp_path):
    s = Stubs(tmp_path, trust_root=BrokenTrustRoot())
    s.trust.kind = "invalid"
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "trust_root_version_unknown")
    assert out.receipt_kind is None
    assert "sign" not in s.calls  # nothing is ever signed on a bad root
    assert s.commit_calls == []


def test_trust_root_unavailable_is_a_refusal_not_a_fallback(tmp_path):
    s = Stubs(tmp_path, trust_root=BrokenTrustRoot())
    s.trust.kind = "generic"
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "trust_root_unavailable")
    assert out.receipt_kind is None
    assert s.commit_calls == []


def test_adjudication_block(tmp_path):
    s = Stubs(tmp_path, adjudicator=lambda r: "block")
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "adjudication_blocked")
    assert out.receipt_kind is None
    assert s.commit_calls == []


def test_adjudication_unknown_refused_never_falls_through(tmp_path):
    # Review finding CRITICAL: unknown decisions used to fall through to
    # admission. Now anything outside {admit, abstain, block} refuses.
    for rogue in ("unknown", "error", "", None, "Admit"):
        s = Stubs(tmp_path, adjudicator=lambda r, _x=rogue: _x)
        out = s.gw.invoke(req(idempotency_key="k-" + str(rogue)))
        assert (out.status, out.reason) == (503, "adjudication_unknown"), rogue
        assert out.receipt_kind is None
        assert out.dependent_writes == []
        assert s.commit_calls == []


def test_unknown_signer_key(tmp_path):
    s = Stubs(tmp_path)
    def boom(r):
        raise SignerKeyUnknown("k99 not in trust root")
    s.gw._signer = boom
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "signer_key_unknown")
    assert out.receipt_kind is None
    assert s.commit_calls == []


def test_signer_unavailable_nothing_committed(tmp_path):
    s = Stubs(tmp_path)
    def boom(r):
        raise SignerUnavailable("offline")
    s.gw._signer = boom
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "signer_unavailable")
    assert out.receipt_kind is None
    assert out.committed_receipt is None
    assert s.commit_calls == []


def test_generic_signer_error_refused(tmp_path):
    s = Stubs(tmp_path)
    def boom(r):
        raise ValueError("signer bug")
    s.gw._signer = boom
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "signer_error")
    assert out.receipt_kind is None
    assert s.commit_calls == []


def test_empty_signature_refused(tmp_path):
    # Review finding: an empty signature would fabricate evidence.
    s = Stubs(tmp_path)
    s.gw._signer = lambda r: ("", "k:yuyay-13")
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "signer_invalid_signature")
    assert out.receipt_kind is None
    assert s.commit_calls == []


def test_khipu_write_failure_is_signed_uncommitted_never_success(tmp_path):
    class BrokenWriter(FileKhipuWriter):
        def append_with_precondition(self, key, receipt, **kwargs):
            raise KhipuWriteError("disk full (simulated)")
    writer = BrokenWriter(str(tmp_path / "khipu.jsonl"))
    s = Stubs(tmp_path, writer=writer)
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "receipt_commit_failed")
    assert out.receipt_kind == "signed-uncommitted"
    assert out.committed_receipt is None
    assert out.dependent_writes == []


# -- successes and their limits ----------------------------------------------

def test_adjudication_abstain_commits_but_releases_nothing(tmp_path):
    s = Stubs(tmp_path, adjudicator=lambda r: "abstain")
    out = s.gw.invoke(req())
    assert out.status == 200
    assert out.reason == "adjudication_abstained"
    assert out.receipt_kind == "abstention"
    assert out.committed_receipt is not None
    assert out.committed_receipt.decision == "abstain"
    assert out.dependent_writes == []
    assert s.commit_calls == ["idem-1"]


def test_admit_happy_path_releases_dependent_write(tmp_path):
    s = Stubs(tmp_path)
    out = s.gw.invoke(req())
    assert out.status == 200
    assert out.reason == "admitted"
    assert out.receipt_kind == "admission"
    ev = out.committed_receipt.event_id
    assert ev.startswith("evt_")
    assert out.dependent_writes == ["released:" + ev]
    assert s.khipu.get("idem-1").event_id == ev


def test_committed_receipt_carries_full_trust_binding(tmp_path):
    s = Stubs(tmp_path)
    out = s.gw.invoke(req())
    r = out.committed_receipt
    assert r.trust_root_version == TRUST_SNAP.version
    assert r.build_digest == TRUST_SNAP.build_digest
    assert r.signer_key_id == "k:yuyay-13"
    assert r.snapshot_digest == SNAP_DIGEST  # full envelope, no empty binds
    assert r.astype_signature  # signed, never half-built


# -- replay -----------------------------------------------------------------

def test_idempotent_replay_returns_original_without_resigning(tmp_path):
    s = Stubs(tmp_path)
    first = s.gw.invoke(req())
    s.calls.clear()
    second = s.gw.invoke(req())
    assert second.status == 200
    assert second.reason == "replayed_original_receipt"
    assert second.committed_receipt.event_id == first.committed_receipt.event_id
    assert "sign" not in s.calls       # replay must not re-sign
    assert "adjudicate" not in s.calls  # replay must not re-adjudicate


def test_replay_of_admission_re_releases_dependent_write(tmp_path):
    # Review finding: a crash between commit and release used to strand the
    # write forever; replay now re-releases (idempotent by event_id).
    s = Stubs(tmp_path)
    first = s.gw.invoke(req())
    second = s.gw.invoke(req())
    ev = first.committed_receipt.event_id
    assert second.receipt_kind == "admission"
    assert second.dependent_writes == ["released:" + ev]
    assert s.commit_calls == ["idem-1"]  # never appended twice


def test_replay_of_abstention_reports_abstention_kind_and_releases_nothing(tmp_path):
    s = Stubs(tmp_path, adjudicator=lambda r: "abstain")
    s.gw.invoke(req(idempotency_key="idem-abs"))
    out = s.gw.invoke(req(idempotency_key="idem-abs"))
    assert out.receipt_kind == "abstention"
    assert out.dependent_writes == []


def test_replay_same_key_different_request_is_conflict_not_poison(tmp_path):
    # Review finding HIGH: same key + different request used to return the
    # OLD receipt as 200. Now: identity mismatch => 409, nothing returned.
    s = Stubs(tmp_path)
    s.gw.invoke(req())
    out = s.gw.invoke(req(args={"payload": "tampered"}))
    assert (out.status, out.reason) == (409, "idempotency_conflict")
    assert out.receipt_kind is None
    assert out.committed_receipt is None
    assert out.dependent_writes == []
    assert s.commit_calls == ["idem-1"]


def test_replay_across_memory_id_is_conflict(tmp_path):
    s = Stubs(tmp_path)
    s.gw.invoke(req())
    out = s.gw.invoke(req(memory_id="mem_999"))
    assert (out.status, out.reason) == (409, "idempotency_conflict")


def test_digest_binds_tenant_so_event_ids_domain_separate(tmp_path):
    # Review finding HIGH: event_id lacked domain separation. The digest now
    # binds tenant + key, so identical memories in two tenants cannot alias.
    s = Stubs(tmp_path)
    a = s.gw.invoke(req(tenant="t:acme", idempotency_key="k-a"))
    s.gw._tenants = lambda t: True
    b = s.gw.invoke(req(tenant="t:other", idempotency_key="k-b"))
    assert a.committed_receipt.event_id != b.committed_receipt.event_id


# -- writer -----------------------------------------------------------------

def _v1_receipt(**over):
    base = dict(
        operation="memory_write",
        memory_id="mem_9",
        operator_subject="p4:PAQ/operator-demo",
        tenant="t:acme",
        request_digest="d" * 64,
        decision="admit",
        trust_root_version=TRUST_SNAP.version,
        build_digest=TRUST_SNAP.build_digest,
        snapshot_digest=SNAP_DIGEST,
        signer_key_id="k:yuyay-13",
        signature="k=szl-yuyay-13;sig=test",
    )
    base.update(over)
    return build_receipt_v1(**base)


def test_writer_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "khipu.jsonl")
    w1 = FileKhipuWriter(path)
    r = _v1_receipt()
    w1.append_with_precondition(
        "key-9", r,
        expect_snapshot_digest=SNAP_DIGEST,
        current_snapshot_digest=lambda: SNAP_DIGEST,
    )
    w2 = FileKhipuWriter(path)
    back = w2.get("key-9")
    assert back is not None
    assert back.event_id == r.event_id
    assert back.astype_signature == "k=szl-yuyay-13;sig=test"
    assert back.snapshot_digest == SNAP_DIGEST  # v1 stays v1 across reload


def test_writer_refuses_silent_overwrite(tmp_path):
    w = FileKhipuWriter(str(tmp_path / "khipu.jsonl"))
    r = _v1_receipt()
    w.append("k", r)
    with pytest.raises(KhipuWriteError):
        w.append("k", r)


def test_writer_never_accepts_new_v0_appends(tmp_path):
    # GPT-6 finding HIGH: "never write new v0 receipts". The writer enforces
    # it, so even a direct caller cannot smuggle a legacy receipt in.
    w = FileKhipuWriter(str(tmp_path / "khipu.jsonl"))
    legacy = build_receipt(
        operation="memory_write",
        memory_id="mem_1",
        operator_subject="p4:PAQ/operator-demo",
        tenant="t:acme",
        request_digest="d" * 64,
        decision="admit",
        signature="sig",
    )
    with pytest.raises(KhipuWriteError):
        w.append("k", legacy)


def test_writer_loads_legacy_v0_readonly(tmp_path):
    # Legacy v0 lines remain loadable for audit (read-only handling).
    path = str(tmp_path / "khipu.jsonl")
    legacy = build_receipt(
        operation="memory_write",
        memory_id="mem_2",
        operator_subject="p4:PAQ/operator-demo",
        tenant="t:acme",
        request_digest="d" * 64,
        decision="admit",
        signature="sig-legacy",
    )
    record = legacy.to_dict()
    record["idempotency_key"] = "old-key"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
        handle.write("\n")
    w = FileKhipuWriter(path)
    back = w.get("old-key")
    assert back is not None
    assert back.schema == RECEIPT_SCHEMA


def test_gate_schema_and_gate_name(tmp_path):
    s = Stubs(tmp_path)
    out = s.gw.invoke(req())
    r = out.committed_receipt
    assert r.schema == "szl.memory-admissibility-receipt/v1"
    assert r.gate == "yuyay-13"
    assert r.canonicalization == "stdlib-json-sortkeys-v1"
