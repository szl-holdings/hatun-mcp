"""Living Anatomy adapter — observe only.

Forge inference law: Anatomy receives a sanitized observation and cannot
modify the decision. Five organs are named. None of them authorize ALLOW.
"""
from __future__ import annotations

from .. import backends as B
from .base import CatalogResult, OrganAdapter, OrganTool, DEFAULT_TIMEOUT

ORGANS = (
    "reasoning_cortex",
    "trust_gate",
    "receipt_bus",
    "consensus",
    "egress",
)


class AnatomyAdapter(OrganAdapter):
    organ = "anatomy"
    base_env = "SZL_ANATOMY_URL"
    base_default = "https://szlholdings-anatomy-3d.hf.space"
    catalog_route = "/"

    async def fetch_catalog(self, timeout: float = DEFAULT_TIMEOUT) -> CatalogResult:
        tools = [
            OrganTool(
                organ=self.organ,
                name="observe",
                description="Accept a sanitized observation event. Cannot change the decision.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "event": {"type": "object"},
                        "decision_hash": {"type": "string"},
                    },
                },
                gate_required=True,
            ),
            OrganTool(
                organ=self.organ,
                name="organs",
                description="List the five anatomy organs. Status only.",
                input_schema={"type": "object"},
            ),
        ]
        return CatalogResult(
            self.organ,
            True,
            tools,
            "local-contract",
            "anatomy.local",
            reason="Observe-only contract. Live 3D reachability is separate.",
        )

    async def call(self, tool: str, args: dict, timeout: float = DEFAULT_TIMEOUT) -> B.BackendResult:
        if tool == "organs":
            return B.BackendResult(
                deployed=True,
                http_status=200,
                endpoint="anatomy.local",
                error=None,
                data={"organs": list(ORGANS), "can_modify_decision": False},
            )
        event = (args or {}).get("event") or {}
        if any(k in event for k in ("allow", "finalize", "execute", "override")):
            return B.BackendResult(
                deployed=True,
                http_status=200,
                endpoint="anatomy.local",
                error=None,
                data={"accepted": False, "reason": "ANATOMY_CANNOT_MODIFY_DECISION"},
            )
        return B.BackendResult(
            deployed=True,
            http_status=200,
            endpoint="anatomy.local",
            error=None,
            data={
                "accepted": True,
                "decision_hash": (args or {}).get("decision_hash"),
                "can_modify_decision": False,
            },
        )
