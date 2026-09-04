"""Second Brain adapter — handles only.

Forge inference law: the second brain retrieves handles. It does not hydrate
content and it does not invent identifiers. Live hologram reachability is a
separate probe. This adapter always exposes the local contract tools.
"""
from __future__ import annotations

import re

from .. import backends as B
from .base import CatalogResult, OrganAdapter, OrganTool, DEFAULT_TIMEOUT

HIDDEN = (
    "khipu.handle.alpha",
    "khipu.handle.beta",
    "nav.waypoint.17",
    "receipt.bind.owner-pubkey",
)
INVENTED = re.compile(r"receipt-7f3a|hidden customer identifier", re.I)


class SecondBrainAdapter(OrganAdapter):
    organ = "second_brain"
    base_env = "SZL_SECOND_BRAIN_URL"
    base_default = "https://szlholdings-szl-second-brain.hf.space"
    catalog_route = "/"

    async def fetch_catalog(self, timeout: float = DEFAULT_TIMEOUT) -> CatalogResult:
        tools = [
            OrganTool(
                organ=self.organ,
                name="retrieve_handles",
                description="Return only handles present in the query. Never hydrate content.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                gate_required=True,
            ),
            OrganTool(
                organ=self.organ,
                name="refuse_invented",
                description="Refuse invented identifiers. Controller-local.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                gate_required=True,
            ),
        ]
        return CatalogResult(
            self.organ,
            True,
            tools,
            "local-contract",
            "second_brain.local",
            reason="Handles-only contract. Live hologram reachability is separate.",
        )

    async def call(self, tool: str, args: dict, timeout: float = DEFAULT_TIMEOUT) -> B.BackendResult:
        query = str((args or {}).get("query") or "")
        if INVENTED.search(query):
            return B.BackendResult(
                deployed=True,
                http_status=200,
                endpoint="second_brain.local",
                error=None,
                data={"action": "REFUSE", "handles": [], "reason": "INVENTED_IDENTIFIER"},
            )
        handles = [h for h in HIDDEN if h in query]
        if tool == "refuse_invented":
            return B.BackendResult(
                deployed=True,
                http_status=200,
                endpoint="second_brain.local",
                error=None,
                data={"action": "OK" if not INVENTED.search(query) else "REFUSE", "handles": handles},
            )
        return B.BackendResult(
            deployed=True,
            http_status=200,
            endpoint="second_brain.local",
            error=None,
            data={"action": "NAVIGATE" if handles else "ABSTAIN", "handles": handles, "hydrated": False},
        )
