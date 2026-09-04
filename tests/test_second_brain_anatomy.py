import asyncio

from hatun_mcp.adapters.anatomy import AnatomyAdapter
from hatun_mcp.adapters.second_brain import SecondBrainAdapter


def test_second_brain_handles_only() -> None:
    ad = SecondBrainAdapter()
    catalog = asyncio.run(ad.fetch_catalog())
    assert catalog.reachable is True
    names = {t.name for t in catalog.tools}
    assert names == {"retrieve_handles", "refuse_invented"}
    hit = asyncio.run(ad.call("retrieve_handles", {"query": "use khipu.handle.alpha only"}))
    assert hit["data"]["handles"] == ["khipu.handle.alpha"]
    assert hit["data"]["hydrated"] is False
    refuse = asyncio.run(ad.call("retrieve_handles", {"query": "look up receipt-7f3a"}))
    assert refuse["data"]["action"] == "REFUSE"


def test_anatomy_cannot_modify_decision() -> None:
    ad = AnatomyAdapter()
    catalog = asyncio.run(ad.fetch_catalog())
    assert catalog.reachable is True
    organs = asyncio.run(ad.call("organs", {}))
    assert organs["data"]["can_modify_decision"] is False
    blocked = asyncio.run(ad.call("observe", {"event": {"allow": True}}))
    assert blocked["data"]["accepted"] is False
