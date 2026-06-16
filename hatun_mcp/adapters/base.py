"""
hatun_mcp.adapters.base — the OrganAdapter interface + dynamic MCP registration.

An adapter does three things, all HONEST about reachability:

  1. fetch_catalog() -> CatalogResult : pull the organ's live MCP tool catalog
     from /api/<organ>/v1/mcp/tools (JSON). Non-200 or non-JSON -> reachable=False
     with a disclosed reason and ZERO tools (never faked).
  2. call(tool, args) -> BackendResult : invoke one organ tool over HTTP. Reuses
     the REAL httpx clients in hatun_mcp.backends (candidate-route fallback + honest
     'route_not_live' disclosure).
  3. probe() -> ProbeResult : liveness, captured from the real HTTP status.

register_organ_tools(mcp, governed, ...) is called once at server startup: it
fetches every adapter's catalog and registers each live organ tool as a real MCP
tool named `<organ>_<tool>`, routed through the existing governed() pipeline so the
Yuyay-13 gate, Khipu receipt, and DSSE envelope all apply uniformly. Unreachable
organs register zero tools + one `<organ>_status` introspection tool.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from .. import backends as B

DEFAULT_TIMEOUT = float(os.environ.get("HATUN_MCP_ADAPTER_TIMEOUT", "8.0"))
# Governance-critical organ tools that must run through the Byzantine quorum.
# Keyed by HONEST organ name (the purged codename backends are now served by the
# live a11oy organs: immune / companion / llm).
GOVERNANCE_CRITICAL = {
    "a11oy": {"policy_evaluate", "lambda_gate", "verdict"},
    "immune": {"verdict", "screen", "policy_evaluate"},
    "companion": {"act"},
    "llm": set(),
    "killinchu": {"evaluate"},
}

# The three previously-codenamed organ backends (sentra/rosie/amaru) were PURGED
# and their capabilities are now served DIRECTLY by the live honest a11oy organs:
#   amaru  → llm        (a11oy LLM tier router / model catalog)
#   sentra → immune     (a11oy Immune (Hukulla) egress policy inspector)
#   rosie  → companion  (a11oy operator / reasoning console)
# Because the adapters are now NAMED for the honest organs, their MCP tools are
# already honest (immune_* / companion_* / llm_*) — no codename ever reaches
# tools/list, so no alias-remapping is needed. VERTICAL_ALIAS is intentionally
# empty; the old codename→alias machinery is retired. See DEPRECATED.md.
VERTICAL_ALIAS: dict[str, str] = {}


def vertical_alias_name(organ: str, leaf: str) -> Optional[str]:
    """Return the alias for an organ tool leaf name, or None. With honest organ
    names there are no aliases to register (VERTICAL_ALIAS is empty)."""
    v = VERTICAL_ALIAS.get(organ)
    return f"{v}_{leaf}" if v else None


@dataclass
class OrganTool:
    """One tool advertised by an organ."""

    organ: str
    name: str                       # organ-local name, e.g. "ask"
    description: str = ""
    input_schema: dict = field(default_factory=lambda: {"type": "object"})
    requires_two_person: bool = False
    gate_required: bool = True
    governance_critical: bool = False

    @property
    def mcp_name(self) -> str:
        """Globally-unique MCP tool name, e.g. 'llm_tiers' / 'immune_screen'."""
        return f"{self.organ}_{self.name}"


@dataclass
class CatalogResult:
    organ: str
    reachable: bool
    tools: list[OrganTool] = field(default_factory=list)
    http_status: Any = None
    source_route: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "organ": self.organ,
            "reachable": self.reachable,
            "tool_count": len(self.tools),
            "tools": [t.mcp_name for t in self.tools],
            "http_status": self.http_status,
            "source_route": self.source_route,
            "reason": self.reason,
        }


@dataclass
class ProbeResult:
    organ: str
    reachable: bool
    http_status: Any
    detail: str = ""


class OrganAdapter:
    """Base adapter. Subclasses set `organ`, `base_env`, `base_default`,
    `catalog_route`, and may override fetch_catalog()/call()."""

    organ: str = "organ"
    base_env: str = ""
    base_default: str = ""
    catalog_route: str = ""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (
            base_url
            or os.environ.get(self.base_env, "")
            or self.base_default
        ).rstrip("/")

    # — liveness ————————————————————————————————————————————————————————————
    async def probe(self, timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
        url = self.base_url + "/"
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                r = await c.get(url)
            return ProbeResult(self.organ, r.status_code < 500, r.status_code,
                               detail=("ok" if r.status_code < 500 else r.text[:160]))
        except (httpx.TimeoutException, httpx.TransportError) as e:
            return ProbeResult(self.organ, False, f"transport_error:{type(e).__name__}",
                               detail=str(e)[:160])

    # — catalog ————————————————————————————————————————————————————————————
    def _parse_catalog_json(self, body: Any, route: str, status: Any) -> CatalogResult:
        """Parse a /v1/mcp/tools JSON body into OrganTools. Accepts either a list of
        dicts (full schemas) or a list of plain string names (defaulted schema)."""
        raw = body.get("tools", body) if isinstance(body, dict) else body
        if not isinstance(raw, list):
            return CatalogResult(self.organ, False, [], status, route,
                                 reason="catalog body was not a list of tools")
        tools: list[OrganTool] = []
        crit = GOVERNANCE_CRITICAL.get(self.organ, set())
        for item in raw:
            if isinstance(item, str):
                name = item
                tools.append(OrganTool(
                    organ=self.organ, name=name,
                    description=f"{self.organ} tool '{name}' (string-name catalog)",
                    governance_critical=name in crit,
                ))
            elif isinstance(item, dict) and item.get("name"):
                name = item["name"]
                tools.append(OrganTool(
                    organ=self.organ, name=name,
                    description=item.get("description", ""),
                    input_schema=item.get("inputSchema", {"type": "object"}),
                    requires_two_person=bool(item.get("requires_two_person", False)),
                    gate_required=bool(item.get("gate_required", True)),
                    governance_critical=name in crit,
                ))
        return CatalogResult(self.organ, True, tools, status, route)

    async def fetch_catalog(self, timeout: float = DEFAULT_TIMEOUT) -> CatalogResult:
        """Default: GET the JSON catalog route. Honest on any failure."""
        route = self.base_url + self.catalog_route
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                r = await c.get(route)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            return CatalogResult(self.organ, False, [], f"transport_error:{type(e).__name__}",
                                 route, reason=f"organ unreachable: {e}")
        if r.status_code != 200:
            body = r.text[:200]
            return CatalogResult(self.organ, False, [], r.status_code, route,
                                 reason=f"catalog route returned {r.status_code}: {body}")
        # Guard against an SPA HTML shell masquerading as 200 (sentra case).
        ctype = r.headers.get("content-type", "")
        if "json" not in ctype and r.text.lstrip()[:1] not in ("[", "{"):
            return CatalogResult(self.organ, False, [], r.status_code, route,
                                 reason="route returned non-JSON (likely SPA HTML shell); "
                                        "no machine-readable tool catalog exposed")
        try:
            body = r.json()
        except (json.JSONDecodeError, ValueError):
            return CatalogResult(self.organ, False, [], r.status_code, route,
                                 reason="route returned 200 but body was not valid JSON")
        return self._parse_catalog_json(body, route, r.status_code)

    # — invocation ————————————————————————————————————————————————————————
    def call_routes(self, tool: str) -> list[str]:
        """Candidate HTTP routes for invoking <tool> on this organ. Subclasses
        may override for organ-specific route shapes."""
        return [
            f"/api/{self.organ}/v1/mcp/call",
            f"/api/{self.organ}/v1/{tool}",
            f"/v1/{tool}",
            f"/{tool}",
        ]

    async def call(self, tool: str, args: dict,
                   timeout: float = DEFAULT_TIMEOUT) -> B.BackendResult:
        """Invoke one organ tool. Reuses the honest _post fallback contract. We POST
        the MCP-style {name,arguments} envelope first, then degrade to the bare args."""
        base = self.base_url
        routes = self.call_routes(tool)
        last_status = None
        payloads = [{"name": tool, "arguments": args or {}}, args or {}]
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for p in routes:
                url = base + p
                for payload in payloads:
                    try:
                        r = await client.post(url, json=payload)
                    except (httpx.TimeoutException, httpx.TransportError) as e:
                        last_status = f"transport_error:{type(e).__name__}"
                        continue
                    last_status = r.status_code
                    if r.status_code == 404:
                        break  # this route absent; try next route
                    try:
                        data = r.json()
                    except (json.JSONDecodeError, ValueError):
                        data = {"raw": r.text[:2000]}
                    return B.BackendResult(
                        deployed=True, http_status=r.status_code, endpoint=url,
                        error=None if r.status_code < 400 else f"http_{r.status_code}",
                        data=data,
                    )
        return B.BackendResult(
            deployed=False, http_status=last_status, endpoint=base + routes[0],
            error="route_not_live",
            reason=(f"{self.organ}.{tool}: no candidate route live (last status "
                    f"{last_status}). Honest stub — disclosed, not faked."),
            data=None,
        )


# ── Dynamic MCP registration ────────────────────────────────────────────────────
def register_organ_tools(
    mcp,
    adapters: dict[str, OrganAdapter],
    governed: Callable,
    *,
    quorum_decider: Optional[Callable] = None,
    catalogs_out: Optional[dict] = None,
) -> dict:
    """Fetch every adapter's catalog and register MCP tools.

    Returns a summary dict {organ: catalog.to_dict()} for the server card / FINAL report.
    Must be called at startup, before mcp.run(). Uses asyncio to fetch catalogs.
    """
    import asyncio

    async def _gather():
        out = {}
        for organ, ad in adapters.items():
            try:
                out[organ] = await ad.fetch_catalog()
            except Exception as e:  # defensive: never let one organ break startup
                out[organ] = CatalogResult(organ, False, [], "exception", "",
                                           reason=f"{type(e).__name__}: {e}")
        return out

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside a loop (rare at import time); run in a fresh loop.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(1) as ex:
                catalogs = ex.submit(lambda: asyncio.run(_gather())).result()
        else:
            catalogs = loop.run_until_complete(_gather())
    except RuntimeError:
        catalogs = asyncio.run(_gather())

    summary = {}
    for organ, cat in catalogs.items():
        ad = adapters[organ]
        summary[organ] = cat.to_dict()
        if cat.reachable and cat.tools:
            for tool in cat.tools:
                _register_one(mcp, ad, tool, governed, quorum_decider)
                # VERTICAL_ALIAS is empty now that organs are honest-named
                # (immune/companion/llm), so this normally yields no alias; it is
                # retained only as a generic hook for any future a11oy-named alias.
                alias = vertical_alias_name(organ, tool.name)
                if alias:
                    _register_one(mcp, ad, tool, governed, quorum_decider, alias_name=alias)
        else:
            _register_status_tool(mcp, ad, cat, governed)
            # Honest a11oy-named status alias for an unreachable aliased organ.
            v = VERTICAL_ALIAS.get(organ)
            if v:
                _register_status_tool(mcp, ad, cat, governed, alias_name=f"{v}_status")
    if catalogs_out is not None:
        catalogs_out.update(catalogs)
    return summary


def _register_one(mcp, adapter: OrganAdapter, tool: OrganTool, governed, quorum_decider,
                  *, alias_name: Optional[str] = None):
    """Register a single live organ tool as an MCP tool routed through governed().

    When `alias_name` is given, the tool is registered under that name as an
    a11oy-vertical alias of `tool.mcp_name` (backward-compat) — routed to the SAME
    organ backend, so the codename and a11oy-named tools are byte-identical in
    behaviour. The Khipu receipt records whichever name the consumer invoked.
    """
    canonical = tool.mcp_name
    name = alias_name or canonical

    async def _impl(arguments: Optional[dict] = None) -> dict:
        args = arguments or {}
        gate_text = json.dumps(args)[:8000] if args else f"{tool.organ}.{tool.name}"
        needs = "write" if tool.requires_two_person else "read"
        return await governed(
            tool=name,
            operation_id=f"{tool.organ}.{tool.name}",
            gate_text=gate_text,
            needs_scope=needs,
            state_changing=tool.requires_two_person,
            backend_coro=adapter.call(tool.name, args),
        )

    # Distinct function name so FastMCP registers a unique tool.
    _impl.__name__ = name
    if alias_name:
        _impl.__doc__ = (
            f"[a11oy {VERTICAL_ALIAS[tool.organ].split('_', 1)[1]}] "
            f"{tool.description or tool.name}. a11oy-named alias of the '{canonical}' "
            f"tool (backward-compat; routes to the same organ backend)"
            + (" · 2-person Yuyay gate required (state-changing)." if tool.requires_two_person else ".")
            + (" · governance-critical: routed through Byzantine quorum." if tool.governance_critical else "")
        )
    else:
        _impl.__doc__ = (
            f"[{tool.organ}] {tool.description or tool.name}. "
            f"Live organ tool aggregated by Hatun-MCP under PURIQ governance"
            + (" · 2-person Yuyay gate required (state-changing)." if tool.requires_two_person else ".")
            + (" · governance-critical: routed through Byzantine quorum." if tool.governance_critical else "")
        )
    mcp.tool(name=name)(_impl)


def _register_status_tool(mcp, adapter: OrganAdapter, cat: CatalogResult, governed,
                          *, alias_name: Optional[str] = None):
    """For an unreachable organ, register exactly one honest status tool.

    When `alias_name` is given, the status tool is also exposed under that
    a11oy-vertical name (e.g. a11oy_sentinel_status) so a11oy-named consumers get
    an honest reachability tool too.
    """
    status_name = alias_name or f"{adapter.organ}_status"

    async def _status(noop: Optional[dict] = None) -> dict:
        probe = await adapter.probe()
        async def _payload():
            return B.BackendResult(
                deployed=False, http_status=probe.http_status,
                endpoint=adapter.base_url, error="organ_unreachable",
                reason=cat.reason or probe.detail,
                data={
                    "organ": adapter.organ,
                    "reachable": probe.reachable,
                    "http_status": probe.http_status,
                    "catalog_reason": cat.reason,
                    "note": ("Honest stub. This organ exposes ZERO MCP tools right now. "
                             "When the organ's Space returns 200 with a JSON catalog, "
                             "Hatun-MCP auto-surfaces its real tools on next restart — "
                             "no fabricated stubs."),
                },
            )
        return await governed(
            tool=status_name, operation_id=f"{adapter.organ}.status",
            gate_text=adapter.organ, needs_scope="read", backend_coro=_payload(),
        )

    _status.__name__ = status_name
    _status.__doc__ = (
        f"[{adapter.organ}] HONEST status. This organ is currently UNREACHABLE "
        f"({cat.reason or 'see payload'}); it exposes zero live MCP tools. "
        f"Call this tool to see why and when it will self-heal."
    )
    mcp.tool(name=status_name)(_status)
