"""Second Brain adapter — measured public handles only.

The controller grant is supplied by the process that constructs this adapter.
Tool arguments cannot authorize a call. The public route returns handles and
evidence digests. Content is not hydrated. Deployment is reported only after
an actual HTTP response from the configured origin.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass

import httpx

from .. import backends as B
from .base import CatalogResult, OrganAdapter, OrganTool, DEFAULT_TIMEOUT

INVENTED = re.compile(r"receipt-7f3a|hidden customer identifier", re.I)
_PIN = re.compile(r"[0-9a-f]{40}\Z")
_PRINCIPAL = re.compile(r"[A-Za-z0-9_.:@/-]{1,128}\Z")
_PRIVATE = {"content", "text", "document", "documents", "body", "raw"}
_HYBRID = "/api/v1/hybrid"
_CAPABILITIES = "/api/v1/retrieval-capabilities"


@dataclass(frozen=True)
class ControllerGrant:
    """Process-owned permission. It is not read from model tool arguments."""

    principal: str
    tenant: str
    scope: str
    purpose: str
    policy_revision: str
    not_before: int
    expires_at: int

    def denial(self, now: int, allowed_tenant: str) -> str | None:
        if (
            not isinstance(self.principal, str)
            or _PRINCIPAL.fullmatch(self.principal) is None
            or not isinstance(self.tenant, str)
            or not self.tenant
            or len(self.tenant) > 128
            or not isinstance(self.policy_revision, str)
            or _PIN.fullmatch(self.policy_revision) is None
            or type(self.not_before) is not int
            or type(self.expires_at) is not int
            or type(now) is not int
        ):
            return "MALFORMED"
        if self.scope != "public_handles" or self.purpose != "public_retrieval":
            return "OUT_OF_SCOPE"
        if self.tenant != allowed_tenant:
            return "WRONG_TENANT"
        if now < self.not_before:
            return "NOT_YET_VALID"
        if now >= self.expires_at:
            return "EXPIRED"
        return None


class _OriginTransport:
    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    async def get(self, url: str):
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            return await client.get(url)

    async def post(self, url: str, payload: dict):
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            return await client.post(url, json=payload)


class SecondBrainAdapter(OrganAdapter):
    organ = "second_brain"
    base_env = "SZL_SECOND_BRAIN_URL"
    base_default = "https://szlholdings-szl-second-brain.hf.space"
    catalog_route = _CAPABILITIES

    def __init__(
        self,
        base_url: str | None = None,
        *,
        grant: ControllerGrant | None = None,
        allowed_tenant: str = "public",
        transport=None,
        clock=None,
    ) -> None:
        super().__init__(base_url)
        self._grant = grant
        self._allowed_tenant = allowed_tenant
        self._transport = transport
        self._clock = clock or time.time

    def _now(self) -> int:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return 0
        return int(value)

    def _transport_for(self, timeout: float):
        return self._transport or _OriginTransport(timeout)

    def _closed(self, code: str, *, state: str, action: str) -> B.BackendResult:
        return B.BackendResult(
            deployed=False,
            http_status=None,
            endpoint=self.base_url + _HYBRID,
            error=code,
            data={
                "state": state,
                "action": action,
                "handles": [],
                "evidence": [],
                "hydrated": False,
                "content_access": "NONE",
                "reason": code,
                "source_revision": None,
            },
        )

    def _grant_code(self) -> str | None:
        if self._grant is None:
            return "GRANT_REQUIRED"
        if not isinstance(self._grant, ControllerGrant):
            return "MALFORMED"
        return self._grant.denial(self._now(), self._allowed_tenant)

    async def fetch_catalog(self, timeout: float = DEFAULT_TIMEOUT) -> CatalogResult:
        code = self._grant_code()
        route = self.base_url + _CAPABILITIES
        if code is not None:
            return CatalogResult(self.organ, False, [], None, route, reason=code)
        try:
            response = await self._transport_for(timeout).get(route)
        except (httpx.TimeoutException, TimeoutError):
            return CatalogResult(self.organ, False, [], "timeout", route, reason="TIMEOUT")
        except (httpx.TransportError, OSError):
            return CatalogResult(self.organ, False, [], "transport", route, reason="BACKEND_UNAVAILABLE")
        if response.status_code in (301, 302, 303, 307, 308) or response.status_code != 200:
            return CatalogResult(
                self.organ, False, [], response.status_code, route, reason="CAPABILITIES_UNAVAILABLE"
            )
        try:
            body = response.json()
        except (ValueError, TypeError):
            return CatalogResult(self.organ, False, [], response.status_code, route, reason="UNEXPECTED_PAYLOAD")
        if (
            not isinstance(body, dict)
            or body.get("public_content_access") != "HANDLES_ONLY"
            or not isinstance(body.get("public_runtime_mode"), str)
        ):
            return CatalogResult(self.organ, False, [], response.status_code, route, reason="UNEXPECTED_PAYLOAD")
        tools = [
            OrganTool(
                organ=self.organ,
                name="retrieve_handles",
                description="Return measured public handles. Never hydrate content.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer"}}},
                gate_required=True,
            ),
            OrganTool(
                organ=self.organ,
                name="refuse_invented",
                description="Refuse invented identifiers before any retrieval.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                gate_required=True,
            ),
        ]
        return CatalogResult(self.organ, True, tools, response.status_code, route, reason="MEASURED")

    async def call(self, tool: str, args: dict, timeout: float = DEFAULT_TIMEOUT) -> B.BackendResult:
        code = self._grant_code()
        if code is not None:
            return self._closed(code, state="DENIED", action="REFUSE")
        if tool not in ("retrieve_handles", "refuse_invented"):
            return self._closed("UNKNOWN_TOOL", state="UNAVAILABLE", action="ABSTAIN")
        parsed = _arguments(args)
        if parsed is None:
            return self._closed("MALFORMED", state="DENIED", action="REFUSE")
        query, k = parsed
        if INVENTED.search(query):
            return self._closed("INVENTED_IDENTIFIER", state="DENIED", action="REFUSE")
        if tool == "refuse_invented" or not query:
            return B.BackendResult(
                deployed=False,
                http_status=None,
                endpoint=self.base_url + _HYBRID,
                error=None,
                data={
                    "state": "ABSTAIN",
                    "action": "OK" if tool == "refuse_invented" else "ABSTAIN",
                    "handles": [],
                    "evidence": [],
                    "hydrated": False,
                    "content_access": "NONE",
                    "reason": "NO_QUERY" if not query else "LOCAL_CLASSIFIER",
                    "source_revision": None,
                },
            )
        url = self.base_url + _HYBRID
        try:
            response = await self._transport_for(timeout).post(url, {"query": query, "k": k})
        except (httpx.TimeoutException, TimeoutError):
            return self._closed("TIMEOUT", state="UNAVAILABLE", action="ABSTAIN")
        except (httpx.TransportError, OSError):
            return self._closed("BACKEND_UNAVAILABLE", state="UNAVAILABLE", action="ABSTAIN")
        return _measured(url, response)


def _arguments(args) -> tuple[str, int] | None:
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return None
    query = args.get("query", "")
    if not isinstance(query, str) or len(query) > 2000:
        return None
    query = query.strip()
    k = args.get("k", 6)
    if type(k) is not int or not 1 <= k <= 12:
        return None
    return query, k


def _measured(url: str, response) -> B.BackendResult:
    status = getattr(response, "status_code", None)
    if status in (301, 302, 303, 307, 308):
        return B.BackendResult(
            deployed=False,
            http_status=status,
            endpoint=url,
            error="REDIRECT",
            data=_empty("UNAVAILABLE", "REDIRECT"),
        )
    if status != 200:
        return B.BackendResult(
            deployed=status is not None,
            http_status=status,
            endpoint=url,
            error="BACKEND_UNAVAILABLE" if status is None or status >= 500 else f"http_{status}",
            data=_empty("UNAVAILABLE", "HTTP_STATUS"),
        )
    text = getattr(response, "text", "")
    if not isinstance(text, str) or len(text) > 65536:
        return B.BackendResult(
            deployed=True, http_status=status, endpoint=url, error="UNEXPECTED_PAYLOAD",
            data=_empty("UNAVAILABLE", "UNEXPECTED_PAYLOAD"),
        )
    try:
        body = response.json()
    except (ValueError, TypeError):
        return B.BackendResult(
            deployed=True, http_status=status, endpoint=url, error="UNEXPECTED_PAYLOAD",
            data=_empty("UNAVAILABLE", "UNEXPECTED_PAYLOAD"),
        )
    admitted = _admit(body)
    if admitted is None:
        return B.BackendResult(
            deployed=True, http_status=status, endpoint=url, error="UNEXPECTED_PAYLOAD",
            data=_empty("UNAVAILABLE", "UNEXPECTED_PAYLOAD"),
        )
    return B.BackendResult(
        deployed=True,
        http_status=status,
        endpoint=url,
        error=None,
        data=admitted,
    )


def _empty(state: str, reason: str) -> dict:
    return {
        "state": state,
        "action": "ABSTAIN",
        "handles": [],
        "evidence": [],
        "hydrated": False,
        "content_access": "NONE",
        "reason": reason,
        "source_revision": None,
    }


def _admit(body) -> dict | None:
    if not isinstance(body, dict) or body.get("content_access") != "HANDLES_ONLY":
        return None
    if _PRIVATE.intersection(body):
        return None
    handles = body.get("handles")
    evidence = body.get("evidence")
    if not isinstance(handles, list) or not isinstance(evidence, list):
        return None
    if len(handles) > 24 or len(evidence) > 24:
        return None
    handle_ids = []
    for item in handles:
        if not isinstance(item, dict) or _PRIVATE.intersection(item):
            return None
        node = item.get("nodeId")
        if not isinstance(node, str) or not node or len(node) > 256:
            return None
        handle_ids.append(node)
    evidence_ids = []
    clean_evidence = []
    for item in evidence:
        if not isinstance(item, dict) or _PRIVATE.intersection(item):
            return None
        node = item.get("node_id")
        source = item.get("source")
        digest = item.get("sha256")
        if (
            not isinstance(node, str)
            or not isinstance(source, str)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            return None
        evidence_ids.append(node)
        clean_evidence.append({"node_id": node, "source": source, "sha256": digest})
    if set(handle_ids) != set(evidence_ids):
        return None
    state = body.get("state")
    if state == "GROUNDED_HANDLES_READY":
        reported = "AVAILABLE"
    elif isinstance(state, str) and state.startswith("ABSTAIN"):
        reported = "ABSTAIN"
    else:
        return None
    if reported == "AVAILABLE" and not clean_evidence:
        reported = "ABSTAIN"
    revision = body.get("generation_sha256")
    if revision is not None and (not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{64}", revision) is None):
        return None
    clean_handles = []
    for item in handles:
        row = {"nodeId": item["nodeId"]}
        kind = item.get("nodeKind")
        label = item.get("label")
        if isinstance(kind, str) and kind and len(kind) <= 64:
            row["nodeKind"] = kind
        if isinstance(label, str) and label and len(label) <= 256:
            row["label"] = label
        clean_handles.append(row)
    return {
        "state": reported,
        "action": "NAVIGATE" if reported == "AVAILABLE" else "ABSTAIN",
        "handles": clean_handles,
        "evidence": clean_evidence,
        "hydrated": False,
        "content_access": "HANDLES_ONLY",
        "reason": "MEASURED",
        "source_revision": revision,
        "upstream_state": state,
    }
