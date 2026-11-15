"""Receipt ownership across caller, auditor, and deferred ledger boundaries."""
import json

import pytest

from hatun_mcp.governance import KhipuChain


class SnapshotSigner:
    def sign(self, packet):
        return {"payload": json.dumps(packet), "signatures": [{"sig": "test-only"}]}


def emit(chain, detail=None):
    return chain.emit(
        tool="local-test", client_id="caller", operation_id="op", status="success",
        tripwire=None, yuyay_min_axis=0.97, hatun_mcp_factor=0.7,
        puriq_score=0.7, detail={} if detail is None else detail,
        signer=SnapshotSigner(),
    )


@pytest.mark.parametrize("surface", ["input", "returned", "dict", "recent"])
def test_public_receipt_surfaces_do_not_rewrite_history(surface):
    detail = {"nested": {"values": [1]}}
    chain = KhipuChain()
    receipt = emit(chain, detail)
    original = chain.recent()
    if surface == "input":
        target = detail
    elif surface == "returned":
        target = receipt.detail
    elif surface == "dict":
        target = receipt.to_dict()["detail"]
    else:
        target = chain.recent()[0]["detail"]
    target["nested"]["values"].append(2)
    assert chain.verify() is True
    assert chain.recent() == original
    assert emit(chain).chain_verified is True


def test_returned_and_audit_signatures_do_not_rewrite_internal_evidence():
    chain = KhipuChain()
    receipt = emit(chain)
    receipt.dsse["signatures"][0]["sig"] = "changed-returned"
    recent = chain.recent()
    recent[0]["dsse"]["signatures"][0]["sig"] = "changed-audit"
    assert chain.recent()[0]["dsse"]["signatures"][0]["sig"] == "test-only"


def test_to_dict_is_a_detached_receipt_snapshot():
    receipt = emit(KhipuChain(), {"nested": [1]})
    snapshot = receipt.to_dict()
    snapshot["detail"]["nested"].append(2)
    snapshot["dsse"]["signatures"].clear()
    assert receipt.detail == {"nested": [1]}
    assert receipt.dsse["signatures"] == [{"sig": "test-only"}]


@pytest.mark.parametrize("direct_forward", [False, True])
def test_deferred_ledger_dispatch_uses_captured_bytes(monkeypatch, direct_forward):
    from hatun_mcp import governance

    pending = []
    captured = []

    class DeferredThread:
        def __init__(self, *, target, daemon):
            pending.append(target)
        def start(self):
            pass

    class Response:
        def close(self):
            pass

    def urlopen(request, *, timeout):
        captured.append(json.loads(request.data))
        return Response()

    monkeypatch.setenv("SZL_RECEIPT_SINK", "https://ledger.invalid")
    monkeypatch.setattr(governance.threading, "Thread", DeferredThread)
    monkeypatch.setattr(governance.urllib.request, "urlopen", urlopen)
    chain = KhipuChain()
    if direct_forward:
        monkeypatch.delenv("SZL_RECEIPT_SINK")
    receipt = emit(chain)
    if direct_forward:
        monkeypatch.setenv("SZL_RECEIPT_SINK", "https://ledger.invalid")
        chain._forward_to_ledger(receipt)
    expected = json.loads(json.dumps(receipt.dsse))
    receipt.dsse["signatures"][0]["sig"] = "changed-before-thread"
    for send in pending:
        send()
    assert captured[0]["dsse"] == expected


def test_forward_serialization_failure_remains_best_effort(monkeypatch):
    monkeypatch.setenv("SZL_RECEIPT_SINK", "https://ledger.invalid")
    chain = KhipuChain()
    monkeypatch.delenv("SZL_RECEIPT_SINK")
    receipt = emit(chain)
    monkeypatch.setenv("SZL_RECEIPT_SINK", "https://ledger.invalid")
    receipt.dsse = {"not_json": object()}
    chain._forward_to_ledger(receipt)
    assert chain.verify() is True
