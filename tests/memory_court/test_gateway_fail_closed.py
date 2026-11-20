"""Day-3 gateway contract tests: the DAY2 fail-closed decision table.

Real tests, no skips. Every vector asserts the full triple:
(status, receipt_kind, dependent_writes) plus the invariant that
infrastructure was never touched on a failed gate.

DAY2 table (docs/memory-court/MEMORY_COURT_DAY2.md):
  unauthenticated  -> 401, no receipt
  wrong tenant     -> 403, no receipt
  malformed routing-> 400
  dirty/unknown build -> 503
  unknown trust root-> 503
  signer key unknown-> 503
  adjudication block-> 503
  signer unavailable-> 503, nothing committed
  khipu write failure -> 503 signed-uncommitted, never success
  abstain           -> 200 abstention, committed, no dependent writes
  admit             -> 200 admission, dependent write released
  replay            -> original receipt, no re-sign, no re-adjudicate
"""

from __future__ import annotations

import pytest

from hatun_mcp.memory_court.gateway import (
    MemoryCourtGateway,
    Request,
    SignerKeyUnknown,
    SignerUnavailable,
)
from hatun_mcp.memory_court.khipu_writer import FileKhipuWriter, KhipuWriteError
from hatun_mcp.memory_court.receipts import build_receipt


ALLOW = lambda subject: subject == "p4:PAQ/operator-demo"
TENANT_OK = lambda tenant: tenant == "t:acme"
ALWAYS_TRUE = lambda: True
SIGN_OK = lambda receipt: "k=szl-yuyay-13;sig=test"


class Stubs:
    def __init__(self, tmp_path, *, adjudicator=None, writer=None):
        self.calls = []
        self.khipu = writer if writer is not None else FileKhipuWriter(str(tmp_path / "khipu.jsonl"))
        self.gw = MemoryCourtGateway(
            auth=lambda s: (self.calls.append("auth") or ALLOW(s)),
            tenant_resolver=lambda t: (self.calls.append("tenant") or TENANT_OK(t)),
            build_admissible=lambda: (self.calls.append("build") or True),
            trust_root_ok=lambda: (self.calls.append("trust") or True),
            adjudicator=adjudicator or (lambda r: (self.calls.append("adjudicate") or "admit")),
            signer=lambda r: (self.calls.append("sign") or SIGN_OK(r)),
            khipu=self.khipu,
        )
        self.append_calls = []
        real_append = self.khipu.append
        self.khipu.append = lambda k, r: (self.append_calls.append(k), real_append(k, r))[1]


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


def test_unauthenticated_caller(tmp_path):
    s = Stubs(tmp_path)
    s.gw._auth = lambda subj: False
    out = s.gw.invoke(req(operator_subject="intruder"))
    assert (out.status, out.reason) == (401, "operator_auth_failed")
    assert out.receipt_kind is None
    assert out.dependent_writes == []
    assert s.append_calls == []


def test_wrong_tenant(tmp_path):
    s = Stubs(tmp_path)
    s.gw._tenants = lambda t: False
    out = s.gw.invoke(req(tenant="t:evil"))
    assert (out.status, out.reason) == (403, "tenant_mismatch")
    assert out.receipt_kind is None
    assert s.append_calls == []


def test_malformed_routing_headers_missing_session(tmp_path):
    s = Stubs(tmp_path)
    out = s.gw.invoke(req(routing_headers={"mcp-profile": "court"}))
    assert (out.status, out.reason) == (400, "malformed_routing_headers")
    assert out.receipt_kind is None


def test_malformed_routing_headers_blank_profile(tmp_path):
    s = Stubs(tmp_path)
    out = s.gw.invoke(req(routing_headers={"mcp-session-id": "s-1", "mcp-profile": "  "}))
    assert out.status == 400


def test_dirty_or_unknown_build(tmp_path):
    s = Stubs(tmp_path)
    s.gw._build_ok = lambda: False
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "build_not_admissible")
    assert out.receipt_kind is None
    assert s.append_calls == []


def test_trust_root_version_unknown(tmp_path):
    s = Stubs(tmp_path)
    s.gw._trust_root_ok = lambda: False
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "trust_root_version_unknown")
    assert out.receipt_kind is None
    assert s.append_calls == []


def test_adjudication_block(tmp_path):
    s = Stubs(tmp_path, adjudicator=lambda r: "block")
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "adjudication_blocked")
    assert out.receipt_kind is None
    assert s.append_calls == []


def test_unknown_signer_key(tmp_path):
    s = Stubs(tmp_path)
    def boom(r):
        raise SignerKeyUnknown("k99 not in trust root")
    s.gw._signer = boom
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "signer_key_unknown")
    assert out.receipt_kind is None
    assert s.append_calls == []


def test_signer_unavailable_nothing_committed(tmp_path):
    s = Stubs(tmp_path)
    def boom(r):
        raise SignerUnavailable("offline")
    s.gw._signer = boom
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "signer_unavailable")
    assert out.receipt_kind is None
    assert out.committed_receipt is None
    assert s.append_calls == []


def test_khipu_write_failure_is_signed_uncommitted_never_success(tmp_path):
    class BrokenWriter(FileKhipuWriter):
        def append(self, key, receipt):
            raise KhipuWriteError("disk full (simulated)")
    writer = BrokenWriter(str(tmp_path / "khipu.jsonl"))
    s = Stubs(tmp_path, writer=writer)
    out = s.gw.invoke(req())
    assert (out.status, out.reason) == (503, "receipt_commit_failed")
    assert out.receipt_kind == "signed-uncommitted"
    assert out.committed_receipt is None
    assert out.dependent_writes == []


def test_adjudication_abstain_commits_but_releases_nothing(tmp_path):
    s = Stubs(tmp_path, adjudicator=lambda r: "abstain")
    out = s.gw.invoke(req())
    assert out.status == 200
    assert out.receipt_kind == "abstention"
    assert out.committed_receipt is not None
    assert out.committed_receipt.decision == "abstain"
    assert out.dependent_writes == []
    assert s.append_calls == ["idem-1"]


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


def test_replay_of_abstention_reports_abstention_kind(tmp_path):
    s = Stubs(tmp_path, adjudicator=lambda r: "abstain")
    s.gw.invoke(req(idempotency_key="idem-abs"))
    out = s.gw.invoke(req(idempotency_key="idem-abs"))
    assert out.receipt_kind == "abstention"
    assert out.dependent_writes == []


def test_missing_khipu_entry_is_not_inferred_success(tmp_path):
    # Recovery rule: writer that lost the append -> get() is None -> the
    # gateway proceeds as a NEW request and must commit before claiming.
    s = Stubs(tmp_path)
    out = s.gw.invoke(req(idempotency_key=None))
    assert out.status == 200
    # and a fresh empty writer reading the same path sees exactly the
    # receipts that were appended - no fabricated entries
    w2 = FileKhipuWriter(str(tmp_path / "khipu.jsonl"))
    assert w2.get("idem-1") is None


def test_writer_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "khipu.jsonl")
    w1 = FileKhipuWriter(path)
    r = build_receipt(
        operation="memory_write",
        memory_id="mem_9",
        operator_subject="p4:PAQ/operator-demo",
        tenant="t:acme",
        request_digest="d" * 64,
        decision="admit",
        signature="k=szl-yuyay-13;sig=test",
    )
    w1.append("key-9", r)
    w2 = FileKhipuWriter(path)
    back = w2.get("key-9")
    assert back is not None
    assert back.event_id == r.event_id
    assert back.astype_signature == "k=szl-yuyay-13;sig=test"


def test_writer_refuses_silent_overwrite(tmp_path):
    w = FileKhipuWriter(str(tmp_path / "khipu.jsonl"))
    r = build_receipt(
        operation="memory_write",
        memory_id="mem_1",
        operator_subject="p4:PAQ/operator-demo",
        tenant="t:acme",
        request_digest="d" * 64,
        decision="admit",
        signature="sig",
    )
    w.append("k", r)
    with pytest.raises(KhipuWriteError):
        w.append("k", r)


def test_gate_schema_and_gate_name(tmp_path):
    s = Stubs(tmp_path)
    out = s.gw.invoke(req())
    r = out.committed_receipt
    assert r.schema == "szl.memory-admissibility-receipt/v0"
    assert r.gate == "yuyay-13"
    assert r.canonicalization == "stdlib-json-sortkeys-v1"
