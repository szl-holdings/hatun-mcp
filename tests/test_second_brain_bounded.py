"""Bounded Second Brain adapter. Transport is in-process and performs no network."""

import asyncio
import json

import pytest

from hatun_mcp.adapters.second_brain import ControllerGrant, SecondBrainAdapter

NOW = 1_700_000_000
PIN = "3a7d935f159abc1b13915dddb6de72ac8eb395a2"


def grant(**overrides):
    base = dict(
        principal="controller.public",
        tenant="public",
        scope="public_handles",
        purpose="public_retrieval",
        policy_revision=PIN,
        not_before=NOW - 10,
        expires_at=NOW + 60,
    )
    base.update(overrides)
    return ControllerGrant(**base)


class Transport:
    def __init__(self, get=None, post=None, error=None):
        self.gets = []
        self.posts = []
        self._get = get
        self._post = post
        self._error = error

    async def get(self, url):
        self.gets.append(url)
        if self._error:
            raise self._error
        return self._get

    async def post(self, url, payload):
        self.posts.append((url, payload))
        if self._error:
            raise self._error
        return self._post


class Response:
    def __init__(self, status_code, payload, content_type="application/json"):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        if isinstance(self._payload, str):
            raise json.JSONDecodeError("not json", self._payload, 0)
        return self._payload


def adapter(transport=None, **grant_overrides):
    return SecondBrainAdapter(
        base_url="https://second-brain.test",
        grant=grant(**grant_overrides),
        transport=transport,
        clock=lambda: NOW,
    )


def grounded(node="node-1"):
    return {
        "schema": "szl.second-brain.hybrid-context/v1",
        "state": "GROUNDED_HANDLES_READY",
        "content_access": "HANDLES_ONLY",
        "handles": [{"nodeId": node, "nodeKind": "INDEX", "label": "DECLARED"}],
        "evidence": [{
            "node_id": node,
            "source": "public-corpus",
            "sha256": "a" * 64,
            "document_revision": "d" * 40,
            "license": "CC-BY-4.0",
            "rights": "public_handles",
            "tenant": "public",
        }],
        "generation_sha256": "b" * 64,
        "evidence_set_sha256": "c" * 64,
    }


def test_missing_grant_does_not_call_transport():
    transport = Transport(post=Response(200, grounded()))
    ad = SecondBrainAdapter(
        base_url="https://second-brain.test",
        transport=transport,
        clock=lambda: NOW,
    )
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    assert result["deployed"] is False
    assert result["data"]["state"] == "DENIED"
    assert result["data"]["handles"] == []
    assert transport.posts == []
    assert transport.gets == []


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"tenant": "other"}, "WRONG_TENANT"),
        ({"expires_at": NOW}, "EXPIRED"),
        ({"not_before": NOW + 1}, "NOT_YET_VALID"),
        ({"scope": "hydrate"}, "OUT_OF_SCOPE"),
        ({"purpose": "train"}, "OUT_OF_SCOPE"),
        ({"policy_revision": "latest"}, "MALFORMED"),
        ({"principal": ""}, "MALFORMED"),
    ],
)
def test_bad_grant_rejects_before_transport(overrides, code):
    transport = Transport(post=Response(200, grounded()))
    ad = adapter(transport, **overrides)
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence", "tenant": "public"}))
    assert result["data"]["reason"] == code
    assert result["data"]["state"] == "DENIED"
    assert result["deployed"] is False
    assert transport.posts == []


def test_model_fields_do_not_authorize():
    transport = Transport(post=Response(200, grounded()))
    ad = SecondBrainAdapter(
        base_url="https://second-brain.test",
        transport=transport,
        clock=lambda: NOW,
    )
    result = asyncio.run(ad.call("retrieve_handles", {
        "query": "coherence",
        "approved": True,
        "tenant": "public",
        "scope": "public_handles",
        "principal": "controller.public",
        "policy_revision": PIN,
    }))
    assert result["data"]["state"] == "DENIED"
    assert transport.posts == []


def test_invented_identifier_and_empty_query_do_not_call_transport():
    transport = Transport(post=Response(200, grounded()))
    ad = adapter(transport)
    refused = asyncio.run(ad.call("retrieve_handles", {"query": "look up receipt-7f3a"}))
    assert refused["data"]["action"] == "REFUSE"
    assert refused["data"]["reason"] == "INVENTED_IDENTIFIER"
    assert refused["data"]["hydrated"] is False
    empty = asyncio.run(ad.call("retrieve_handles", {"query": "   "}))
    assert empty["data"]["state"] == "ABSTAIN"
    assert transport.posts == []


def test_malformed_arguments_do_not_call_transport():
    transport = Transport(post=Response(200, grounded()))
    ad = adapter(transport)
    result = asyncio.run(ad.call("retrieve_handles", {"query": 12, "k": True}))
    assert result["data"]["reason"] == "MALFORMED"
    assert transport.posts == []


def test_measured_public_handles_keep_digest_and_do_not_hydrate():
    payload = grounded()
    transport = Transport(post=Response(200, payload))
    ad = adapter(transport)
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence", "k": 6}))
    assert transport.posts == [(
        "https://second-brain.test/api/v1/hybrid",
        {"query": "coherence", "k": 6},
    )]
    assert result["deployed"] is True
    assert result["http_status"] == 200
    assert result["error"] is None
    assert result["data"]["hydrated"] is False
    assert result["data"]["handles"] == payload["handles"]
    assert result["data"]["evidence"] == payload["evidence"]
    assert result["data"]["source_revision"] == "b" * 64
    assert "documents" not in result["data"]


def test_query_echo_handle_is_not_invented_when_backend_abstains():
    payload = {
        "state": "ABSTAIN_NO_GROUNDED_HANDLES",
        "content_access": "HANDLES_ONLY",
        "handles": [],
        "evidence": [],
        "generation_sha256": "b" * 64,
    }
    transport = Transport(post=Response(200, payload))
    ad = adapter(transport)
    result = asyncio.run(ad.call("retrieve_handles", {"query": "use khipu.handle.alpha only"}))
    assert result["data"]["handles"] == []
    assert result["data"]["state"] == "ABSTAIN"
    assert result["data"]["hydrated"] is False


def test_private_payload_is_not_returned():
    payload = grounded()
    payload["documents"] = [{"text": "private"}]
    transport = Transport(post=Response(200, payload))
    ad = adapter(transport)
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    assert result["data"]["handles"] == []
    assert result["data"]["state"] == "UNAVAILABLE"
    assert "private" not in json.dumps(result["data"])


def test_timeout_and_unreachable_backend():
    import httpx

    timed = Transport(error=httpx.TimeoutException("deadline"))
    ad = adapter(timed)
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    assert result["deployed"] is False
    assert result["http_status"] is None
    assert result["data"]["reason"] == "TIMEOUT"
    assert result["data"]["evidence"] == []
    assert result["data"]["handles"] == []
    down = Transport(error=httpx.ConnectError("refused"))
    ad = adapter(down)
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    assert result["deployed"] is False
    assert result["http_status"] is None
    assert result["data"]["reason"] == "BACKEND_UNAVAILABLE"
    assert result["data"]["evidence"] == []
    assert result["data"]["state"] == "UNAVAILABLE"


def test_catalog_reachability_comes_from_the_capabilities_response():
    good = {
        "public_content_access": "HANDLES_ONLY",
        "public_runtime_mode": "BM25_ONLY",
    }
    transport = Transport(get=Response(200, good))
    ad = adapter(transport)
    catalog = asyncio.run(ad.fetch_catalog())
    assert catalog.reachable is True
    assert {tool.name for tool in catalog.tools} == {"retrieve_handles", "refuse_invented"}
    assert transport.gets == ["https://second-brain.test/api/v1/retrieval-capabilities"]
    denied = SecondBrainAdapter(base_url="https://second-brain.test", transport=transport, clock=lambda: NOW)
    catalog = asyncio.run(denied.fetch_catalog())
    assert catalog.reachable is False
    assert catalog.tools == []
    gets_after_catalog = list(transport.gets)
    probe = asyncio.run(denied.probe())
    assert probe.reachable is False
    assert probe.http_status is None
    assert transport.gets == gets_after_catalog


def test_policy_evaluate_is_not_retrieval():
    transport = Transport(post=Response(200, grounded("khipu.handle.alpha")))
    ad = adapter(transport)
    result = asyncio.run(ad.call("policy_evaluate", {"query": "use khipu.handle.alpha only", "k": 6}))
    assert result["deployed"] is False
    assert result["http_status"] is None
    assert result["data"]["reason"] == "UNSUPPORTED_OPERATION"
    assert result["data"]["handles"] == []
    assert result["data"]["evidence"] == []
    assert result["data"]["action"] == "ABSTAIN"
    assert "khipu.handle.alpha" not in json.dumps(result["data"])
    assert transport.posts == []
    assert transport.gets == []


def test_uncertain_backend_returns_empty_evidence():
    payload = {
        "state": "UNCERTAIN",
        "content_access": "HANDLES_ONLY",
        "handles": [{"nodeId": "node-1"}],
        "evidence": [{"node_id": "node-1", "source": "public-corpus", "sha256": "a" * 64}],
    }
    transport = Transport(post=Response(200, payload))
    ad = adapter(transport)
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    assert result["data"]["state"] == "UNCERTAIN"
    assert result["data"]["handles"] == []
    assert result["data"]["evidence"] == []
    assert result["data"]["hydrated"] is False


def test_local_catalog_is_not_public_reached():
    from hatun_mcp.state import _organ_registration

    local = _organ_registration({
        "second_brain": {"reachable": True, "tools": 2, "http_status": "local-contract"},
    })
    assert local["organs"][0]["reachability"] == "STRUCTURAL-ONLY"
    measured = _organ_registration({
        "second_brain": {"reachable": True, "tools": 2, "http_status": 200},
    })
    assert measured["organs"][0]["reachability"] == "REACHED"
    absent = _organ_registration({
        "second_brain": {"reachable": False, "tools": 0, "http_status": None},
    })
    assert absent["organs"][0]["reachability"] == "UNAVAILABLE"


def test_unusable_clock_does_not_authorize_a_zero_time_grant():
    transport = Transport(post=Response(200, grounded()))
    ad = SecondBrainAdapter(
        base_url="https://second-brain.test",
        grant=grant(not_before=-5, expires_at=60),
        transport=transport,
        clock=lambda: float("nan"),
    )
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    assert result["deployed"] is False
    assert result["data"]["reason"] == "MALFORMED"
    assert transport.posts == []


def test_missing_rights_abstain_without_releasing_handles():
    payload = grounded()
    for row in payload["evidence"]:
        row.pop("license")
        row.pop("rights")
    transport = Transport(post=Response(200, payload))
    ad = adapter(transport)
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    assert result["data"]["state"] == "ABSTAIN"
    assert result["data"]["reason"] == "RIGHTS_UNBOUND"
    assert result["data"]["handles"] == []
    assert result["data"]["evidence"] == []
    assert result["data"]["execution_authority"] == "NONE"


def test_withdrawn_source_is_not_released():
    payload = grounded()
    payload["evidence"][0]["rights"] = "withdrawn"
    transport = Transport(post=Response(200, payload))
    result = asyncio.run(adapter(transport).call("retrieve_handles", {"query": "coherence"}))
    assert result["data"]["state"] == "ABSTAIN"
    assert result["data"]["reason"] == "WITHDRAWN"
    assert result["data"]["evidence"] == []
    assert result["data"]["handles"] == []


def test_evidence_tenant_change_is_denied():
    payload = grounded()
    payload["evidence"][0]["tenant"] = "other"
    transport = Transport(post=Response(200, payload))
    result = asyncio.run(adapter(transport).call("retrieve_handles", {"query": "coherence"}))
    assert result["data"]["state"] == "DENIED"
    assert result["data"]["reason"] == "WRONG_TENANT"
    assert result["data"]["evidence"] == []


def test_authority_claim_is_not_promoted():
    payload = grounded()
    payload["execution_authority"] = "EXECUTE"
    transport = Transport(post=Response(200, payload))
    result = asyncio.run(adapter(transport).call("retrieve_handles", {"query": "coherence"}))
    assert result["data"]["state"] == "DENIED"
    assert result["data"]["reason"] == "AUTHORITY_PROMOTION"
    assert result["data"]["execution_authority"] == "NONE"
    assert result["data"]["handles"] == []
    assert "EXECUTE" not in json.dumps(result["data"])


def test_replay_does_not_post_twice_and_conflict_does_not_post():
    transport = Transport(post=Response(200, grounded()))
    ad = adapter(transport)
    first = asyncio.run(ad.call("retrieve_handles", {"query": "coherence", "operation_id": "op-1"}))
    second = asyncio.run(ad.call("retrieve_handles", {"query": "coherence", "operation_id": "op-1"}))
    assert first["data"]["state"] == "AVAILABLE"
    assert second["data"]["evidence"] == first["data"]["evidence"]
    assert len(transport.posts) == 1
    conflict = asyncio.run(ad.call("retrieve_handles", {"query": "other", "operation_id": "op-1"}))
    assert conflict["data"]["reason"] == "REPLAY_CONFLICT"
    assert conflict["data"]["state"] == "DENIED"
    assert len(transport.posts) == 1


def test_grant_expiring_before_release_drops_handles():
    ticks = iter((NOW, NOW + 1000))
    transport = Transport(post=Response(200, grounded()))
    ad = SecondBrainAdapter(
        base_url="https://second-brain.test",
        grant=grant(),
        transport=transport,
        clock=lambda: next(ticks),
    )
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    assert len(transport.posts) == 1
    assert result["data"]["state"] == "DENIED"
    assert result["data"]["reason"] == "EXPIRED"
    assert result["data"]["handles"] == []
    assert result["data"]["evidence"] == []


def test_egress_rechecks_grant_and_does_not_call_transport():
    transport = Transport(post=Response(200, grounded()))
    ad = adapter(transport)
    admitted = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    released = ad.release_for_egress(admitted["data"])
    assert released["execution_authority"] == "NONE"
    assert released["tenant"] == "public"
    assert len(transport.posts) == 1
    expired = SecondBrainAdapter(
        base_url="https://second-brain.test",
        grant=grant(expires_at=NOW),
        transport=transport,
        clock=lambda: NOW,
    )
    denied = expired.release_for_egress(admitted["data"])
    assert denied["state"] == "DENIED"
    assert denied["reason"] == "EXPIRED"
    assert denied["evidence"] == []
    assert len(transport.posts) == 1


def test_registered_read_tool_does_not_become_a_write():
    from hatun_mcp.adapters.base import OrganTool, _register_one

    recorded = {}

    class MCP:
        def tool(self, name=None):
            def deco(fn):
                recorded["fn"] = fn
                recorded["name"] = name
                return fn
            return deco

    async def governed(**kwargs):
        recorded["scope"] = kwargs["needs_scope"]
        recorded["state_changing"] = kwargs["state_changing"]
        return await kwargs["backend_coro"]

    transport = Transport(post=Response(200, grounded()))
    ad = adapter(transport)
    tool = OrganTool(
        organ="second_brain",
        name="retrieve_handles",
        description="Return measured public handles. Never hydrate content.",
        input_schema={"type": "object"},
        gate_required=True,
    )
    _register_one(MCP(), ad, tool, governed, None)
    result = asyncio.run(recorded["fn"]({"query": "coherence", "k": 6}))
    assert recorded["name"] == "second_brain_retrieve_handles"
    assert recorded["scope"] == "read"
    assert recorded["state_changing"] is False
    assert result["data"]["execution_authority"] == "NONE"
    assert result["data"]["evidence"][0]["rights"] == "public_handles"
    assert result["data"]["evidence"][0]["tenant"] == "public"
    assert len(transport.posts) == 1


def test_unbounded_abstain_state_is_not_copied():
    payload = grounded()
    payload["state"] = "ABSTAIN_" + ("X" * 4000)
    payload["handles"] = []
    payload["evidence"] = []
    transport = Transport(post=Response(200, payload))
    ad = adapter(transport)
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    assert result["data"]["state"] == "UNAVAILABLE"
    assert "XXXX" not in json.dumps(result["data"])


def test_timeout_then_conflicting_query_does_not_post():
    import httpx

    transport = Transport(error=httpx.TimeoutException("deadline"))
    ad = adapter(transport)
    first = asyncio.run(ad.call("retrieve_handles", {"query": "coherence", "operation_id": "op-t"}))
    assert first["data"]["state"] == "UNAVAILABLE"
    assert first["data"]["reason"] == "TIMEOUT"
    assert first["data"]["handles"] == []
    assert len(transport.posts) == 1
    conflict = asyncio.run(ad.call("retrieve_handles", {"query": "other", "operation_id": "op-t"}))
    assert conflict["data"]["state"] == "DENIED"
    assert conflict["data"]["reason"] == "REPLAY_CONFLICT"
    assert conflict["data"]["handles"] == []
    assert len(transport.posts) == 1
    replay = asyncio.run(ad.call("retrieve_handles", {"query": "coherence", "operation_id": "op-t"}))
    assert replay["data"]["reason"] == "TIMEOUT"
    assert len(transport.posts) == 1


def test_replay_capacity_refuses_a_new_operation_without_a_post():
    transport = Transport(post=Response(200, grounded()))
    ad = adapter(transport)
    for index in range(32):
        admitted = asyncio.run(ad.call(
            "retrieve_handles",
            {"query": "coherence", "operation_id": f"op-{index}"},
        ))
        assert admitted["data"]["state"] == "AVAILABLE"
    assert len(transport.posts) == 32
    blocked = asyncio.run(ad.call("retrieve_handles", {"query": "coherence", "operation_id": "op-extra"}))
    assert blocked["data"]["state"] == "DENIED"
    assert blocked["data"]["reason"] == "REPLAY_CAPACITY"
    assert blocked["data"]["handles"] == []
    assert len(transport.posts) == 32
    retained = asyncio.run(ad.call("retrieve_handles", {"query": "coherence", "operation_id": "op-0"}))
    assert retained["data"]["state"] == "AVAILABLE"
    assert retained["data"]["evidence"]
    assert len(transport.posts) == 32


def test_in_flight_operation_does_not_post_twice():
    started = asyncio.Event()
    release = asyncio.Event()
    posts = []

    class Gated:
        async def post(self, url, payload):
            posts.append(payload)
            started.set()
            await release.wait()
            return Response(200, grounded())

    ad = adapter(Gated())

    async def scenario():
        first = asyncio.create_task(ad.call(
            "retrieve_handles",
            {"query": "coherence", "operation_id": "op-c"},
        ))
        await started.wait()
        second = await ad.call("retrieve_handles", {"query": "coherence", "operation_id": "op-c"})
        assert second["data"]["state"] == "UNAVAILABLE"
        assert second["data"]["reason"] == "REPLAY_IN_FLIGHT"
        assert second["data"]["handles"] == []
        assert len(posts) == 1
        release.set()
        admitted = await first
        assert admitted["data"]["state"] == "AVAILABLE"
        assert len(posts) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("state", [["UNCERTAIN"], {"status": "UNCERTAIN"}])
def test_non_string_upstream_state_is_a_closed_malformed_response(state):
    payload = grounded()
    payload["state"] = state
    transport = Transport(post=Response(200, payload))
    ad = adapter(transport)
    result = asyncio.run(ad.call("retrieve_handles", {"query": "coherence"}))
    assert result["data"]["state"] == "UNAVAILABLE"
    assert result["data"]["reason"] == "MALFORMED_RESPONSE"
    assert result["data"]["handles"] == []
    assert result["data"]["evidence"] == []
    assert result["data"]["hydrated"] is False
    assert "UNCERTAIN" not in json.dumps(result["data"])
