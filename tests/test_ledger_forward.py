"""Ledger-forward must be strictly fire-and-forget: emit() keeps working and the
Khipu chain stays intact even when SZL_RECEIPT_SINK is unreachable."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hatun_mcp.governance import KhipuChain  # noqa: E402


def _emit(c, **over):
    kw = dict(
        tool="t", client_id="c", operation_id="op", status="success",
        tripwire=None, yuyay_min_axis=0.97, hatun_mcp_factor=0.7,
        puriq_score=0.7, detail={},
    )
    kw.update(over)
    return c.emit(**kw)


def test_emit_works_when_sink_unreachable(monkeypatch):
    # Point the sink at a closed port; the forward must not raise or block.
    monkeypatch.setenv("SZL_RECEIPT_SINK", "http://127.0.0.1:9")
    c = KhipuChain()
    r1 = _emit(c)
    r2 = _emit(c)
    assert r2.prev_hash == r1.continuum_hash
    assert c.verify() is True
    # Give the daemon thread a moment; its failure must stay swallowed.
    time.sleep(0.2)
    assert c.verify() is True


def test_emit_works_with_no_sink_configured(monkeypatch):
    monkeypatch.delenv("SZL_RECEIPT_SINK", raising=False)
    c = KhipuChain()
    r = _emit(c)
    assert r.continuum_hash and c.verify() is True


def test_forward_never_raises(monkeypatch):
    monkeypatch.setenv("SZL_RECEIPT_SINK", "http://127.0.0.1:9")
    c = KhipuChain()
    r = _emit(c)
    # Direct call must also be silent regardless of network outcome.
    c._forward_to_ledger(r)
