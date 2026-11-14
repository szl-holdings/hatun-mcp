"""Default aggregation keys must not be reproducible in another process."""
import json
import os
from unittest.mock import patch
import pytest
from hatun_mcp import dsse


@pytest.mark.skipif(not dsse._HAS_BLS, reason="requires real py_ecc BLS backend")
def test_default_aggregators_do_not_share_signing_keys():
    with patch.dict(os.environ, {}, clear=True):
        first = dsse.BlsAggregator()
        second = dsse.BlsAggregator()
    receipts = [("a11oy", "11" * 32), ("immune", "22" * 32)]
    signature = first.aggregate(receipts)
    assert first.public_key("a11oy") != second.public_key("a11oy")
    assert first.verify(receipts, signature.aggregate)
    assert not second.verify(receipts, signature.aggregate)


@pytest.mark.skipif(not dsse._HAS_BLS, reason="requires real py_ecc BLS backend")
def test_legacy_public_seed_cannot_reproduce_default_keys():
    with patch.dict(os.environ, {}, clear=True):
        current = dsse.BlsAggregator()
    public_default = dsse.BlsAggregator(seed="hatun-mcp-doctrine-v11")
    receipts = [("a11oy", "33" * 32)]
    forged = public_default.aggregate(receipts)
    assert not current.verify(receipts, forged.aggregate)


@pytest.mark.skipif(not dsse._HAS_BLS, reason="requires real py_ecc BLS backend")
def test_explicit_seed_is_reproducible_and_response_binds_public_keys():
    first = dsse.BlsAggregator(seed="test-only-private-fixture")
    second = dsse.BlsAggregator(seed="test-only-private-fixture")
    receipts = [("a11oy", "44" * 32), ("immune", "55" * 32)]
    out = first.aggregate(receipts)
    assert second.verify(receipts, out.aggregate)
    value = out.to_dict()
    assert value["key_source"] == "configured"
    assert value["ephemeral"] is False
    assert value["signer_scope"] == "aggregator-process"
    assert value["independent_organ_attestations"] is False
    assert dsse._BLS.AggregateVerify(
        [bytes.fromhex(pk) for pk in value["public_keys"]],
        [bytes.fromhex(digest) for digest in value["receipt_hashes"]],
        bytes.fromhex(value["aggregate_signature"]),
    )
    assert "test-only-private-fixture" not in json.dumps(value)


def test_environment_seed_and_empty_environment():
    with patch.dict(os.environ, {"HATUN_MCP_BLS_SEED": "env-test-fixture"}, clear=True):
        configured = dsse.BlsAggregator()
        explicit = dsse.BlsAggregator(seed="explicit-test-fixture")
    assert configured.seed == "env-test-fixture"
    assert configured.ephemeral is False
    assert explicit.seed == "explicit-test-fixture"
    with patch.dict(os.environ, {"HATUN_MCP_BLS_SEED": ""}, clear=True):
        ephemeral = dsse.BlsAggregator()
    assert ephemeral.ephemeral is True
    assert len(ephemeral.seed) == 64


def test_unsigned_fallback_does_not_claim_a_signing_identity():
    with patch.object(dsse, "_HAS_BLS", False):
        result = dsse.BlsAggregator().aggregate([("a11oy", "66" * 32)]).to_dict()
    assert result["mode"] == "MERKLE-AGG"
    assert result["signer_scope"] == "unsigned"
    assert result["public_keys"] == []
    assert result["key_source"] == "none"
    assert result["independent_organ_attestations"] is False
