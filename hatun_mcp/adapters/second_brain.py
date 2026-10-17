"""Second Brain adapter — measured public handles only.

The controller grant is supplied by the process that constructs this adapter.
Tool arguments cannot authorize a call. The public route returns handles and
evidence digests. Content is not hydrated. Deployment is reported only after
an actual HTTP response from the configured origin.
"""
from __future__ import annotations

import copy
import math
import re
import time
from dataclasses import dataclass

import httpx

from .. import backends as B
from .base import CatalogResult, OrganAdapter, OrganTool, ProbeResult, DEFAULT_TIMEOUT

INVENTED = re.compile(r"receipt-7f3a|hidden customer identifier", re.I)
_PIN = re.compile(r"[0-9a-f]{40}\Z")
_PRINCIPAL = re.compile(r"[A-Za-z0-9_.:@/-]{1,128}\Z")
_UPSTREAM = re.compile(r"(?:GROUNDED_HANDLES_READY|ABSTAIN(?:_[A-Z0-9_]{1,64})?)\Z")
_LICENSE = re.compile(r"[A-Za-z0-9.+-]{1,64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z|[0-9a-f]{64}\Z")
_OPERATION = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_PRIVATE = {"content", "text", "document", "documents", "body", "raw"}
_RIGHTS_OK = frozenset({"public_handles", "public_citation"})
_RIGHTS_WITHDRAWN = frozenset({"withdrawn", "revoked"})
_HYBRID = "/api/v1/hybrid"
_CAPABILITIES = "/api/v1/retrieval-capabilities"
_REPLAY_LIMIT = 32


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
        self._replay: dict[str, tuple] = {}
        self._replay_order: list[str] = []

    def _now(self) -> int | None:
        try:
            value = self._clock()
        except Exception:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return None
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
                "execution_authority": "NONE",
                "tenant": None,
            },
        )

    def _grant_code(self) -> str | None:
        if self._grant is None:
            return "GRANT_REQUIRED"
        if not isinstance(self._grant, ControllerGrant):
            return "MALFORMED"
        now = self._now()
        if now is None:
            return "MALFORMED"
        return self._grant.denial(now, self._allowed_tenant)

    async def fetch_catalog(self, timeout: float = DEFAULT_TIMEOUT) -> CatalogResult:
        code = self._grant_code()
        route = self.base_url + _CAPABILITIES
        if code is not None:
            return CatalogResult(self.organ, False, [], None, route, reason=code)
        try:
            response = await self._transport_for(timeout).get(route)
        except (httpx.TimeoutException, TimeoutError):
            return CatalogResult(self.organ, False, [], "timeout", route, reason="TIMEOUT")
        except (httpx.HTTPError, OSError):
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

    async def probe(self, timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
        code = self._grant_code()
        if code is not None:
            return ProbeResult(self.organ, False, None, detail=code)
        try:
            response = await self._transport_for(timeout).get(self.base_url + _CAPABILITIES)
        except (httpx.TimeoutException, TimeoutError):
            return ProbeResult(self.organ, False, None, detail="TIMEOUT")
        except (httpx.HTTPError, OSError):
            return ProbeResult(self.organ, False, None, detail="BACKEND_UNAVAILABLE")
        status = getattr(response, "status_code", None)
        if status != 200:
            return ProbeResult(self.organ, False, status, detail="CAPABILITIES_UNAVAILABLE")
        try:
            body = response.json()
        except (ValueError, TypeError):
            return ProbeResult(self.organ, False, status, detail="UNEXPECTED_PAYLOAD")
        reachable = (
            isinstance(body, dict)
            and body.get("public_content_access") == "HANDLES_ONLY"
            and isinstance(body.get("public_runtime_mode"), str)
        )
        return ProbeResult(
            self.organ,
            reachable,
            status,
            detail="MEASURED" if reachable else "UNEXPECTED_PAYLOAD",
        )

    def _remember(self, operation: str, key: tuple, result: B.BackendResult) -> None:
        if operation not in self._replay:
            if len(self._replay) >= _REPLAY_LIMIT:
                return
            self._replay_order.append(operation)
        self._replay[operation] = (key, copy.deepcopy(result))

    def _stored(self, operation: str, key: tuple, result: B.BackendResult) -> B.BackendResult:
        if operation:
            self._remember(operation, key, result)
        return result

    def _replay_gate(self, operation: str, key: tuple) -> B.BackendResult | None:
        held = self._replay.get(operation)
        if held is not None:
            cached_key, cached = held
            if cached_key != key:
                return self._closed("REPLAY_CONFLICT", state="DENIED", action="REFUSE")
            if cached is None:
                return self._closed("REPLAY_IN_FLIGHT", state="UNAVAILABLE", action="ABSTAIN")
            return self._release(copy.deepcopy(cached))
        if len(self._replay) >= _REPLAY_LIMIT:
            return self._closed("REPLAY_CAPACITY", state="DENIED", action="REFUSE")
        self._replay[operation] = (key, None)
        self._replay_order.append(operation)
        return None

    def _release(self, result: B.BackendResult) -> B.BackendResult:
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if data.get("execution_authority") not in (None, "NONE") or data.get("execution_authorized") not in (None, False):
            return self._closed("AUTHORITY_PROMOTION", state="DENIED", action="REFUSE")
        code = self._grant_code()
        if code is not None:
            return self._closed(code, state="DENIED", action="REFUSE")
        released = dict(data)
        released["execution_authority"] = "NONE"
        if released.get("state") in {"AVAILABLE", "ABSTAIN", "UNCERTAIN"}:
            released["tenant"] = self._allowed_tenant
        return B.BackendResult(
            deployed=result.get("deployed"),
            http_status=result.get("http_status"),
            endpoint=result.get("endpoint"),
            error=result.get("error"),
            data=released,
        )

    def release_for_egress(self, data: dict) -> dict:
        """Recheck the grant before a result can leave the process.

        This does not call the origin and it does not grant execution.
        """
        if not isinstance(data, dict):
            return self._closed("MALFORMED", state="DENIED", action="REFUSE")["data"]
        if data.get("execution_authority") not in (None, "NONE") or data.get("execution_authorized") not in (None, False):
            return self._closed("AUTHORITY_PROMOTION", state="DENIED", action="REFUSE")["data"]
        code = self._grant_code()
        if code is not None:
            return self._closed(code, state="DENIED", action="REFUSE")["data"]
        if data.get("state") == "AVAILABLE":
            evidence = data.get("evidence")
            if not isinstance(evidence, list) or not evidence or any(not _bound_row(row, self._allowed_tenant) for row in evidence):
                return self._closed("RIGHTS_UNBOUND", state="ABSTAIN", action="ABSTAIN")["data"]
        released = dict(data)
        released["execution_authority"] = "NONE"
        released["hydrated"] = False
        released["tenant"] = self._allowed_tenant
        return released

    async def call(self, tool: str, args: dict, timeout: float = DEFAULT_TIMEOUT) -> B.BackendResult:
        if tool not in ("retrieve_handles", "refuse_invented"):
            return self._closed("UNSUPPORTED_OPERATION", state="UNAVAILABLE", action="ABSTAIN")
        operation, operation_error = _operation(args)
        if operation_error is not None:
            return self._closed("MALFORMED", state="DENIED", action="REFUSE")
        parsed = _arguments(args)
        if parsed is None:
            return self._closed("MALFORMED", state="DENIED", action="REFUSE")
        code = self._grant_code()
        if code is not None:
            return self._closed(code, state="DENIED", action="REFUSE")
        query, k = parsed
        key = (tool, query, k)
        if operation:
            replayed = self._replay_gate(operation, key)
            if replayed is not None:
                return replayed
        if INVENTED.search(query):
            return self._stored(operation, key, self._closed("INVENTED_IDENTIFIER", state="DENIED", action="REFUSE"))
        if tool == "refuse_invented" or not query:
            result = B.BackendResult(
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
                    "execution_authority": "NONE",
                    "tenant": self._allowed_tenant,
                },
            )
            return self._stored(operation, key, result)
        url = self.base_url + _HYBRID
        try:
            response = await self._transport_for(timeout).post(url, {"query": query, "k": k})
        except (httpx.TimeoutException, TimeoutError):
            return self._stored(operation, key, self._closed("TIMEOUT", state="UNAVAILABLE", action="ABSTAIN"))
        except (httpx.HTTPError, OSError):
            return self._stored(operation, key, self._closed("BACKEND_UNAVAILABLE", state="UNAVAILABLE", action="ABSTAIN"))
        return self._stored(operation, key, self._release(_measured(url, response, self._allowed_tenant)))


def _operation(args) -> tuple[str, str | None]:
    if not isinstance(args, dict) or "operation_id" not in args:
        return "", None
    value = args.get("operation_id")
    if not isinstance(value, str) or _OPERATION.fullmatch(value) is None:
        return "", "MALFORMED"
    return value, None


def _bound_row(item, allowed_tenant: str) -> bool:
    if not isinstance(item, dict):
        return False
    revision = item.get("document_revision")
    license_name = item.get("license")
    return (
        isinstance(item.get("node_id"), str)
        and isinstance(item.get("source"), str)
        and isinstance(item.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None
        and isinstance(revision, str)
        and _REVISION.fullmatch(revision) is not None
        and isinstance(license_name, str)
        and _LICENSE.fullmatch(license_name) is not None
        and item.get("rights") in _RIGHTS_OK
        and item.get("tenant") == allowed_tenant
    )


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


def _measured(url: str, response, allowed_tenant: str) -> B.BackendResult:
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
    admitted = _admit(body, allowed_tenant)
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
        "execution_authority": "NONE",
        "tenant": None,
    }


def _held(state: str, reason: str, action: str) -> dict:
    return {
        "state": state,
        "action": action,
        "handles": [],
        "evidence": [],
        "hydrated": False,
        "content_access": "NONE" if state == "DENIED" else "HANDLES_ONLY",
        "reason": reason,
        "source_revision": None,
        "execution_authority": "NONE",
        "tenant": None,
    }


def _admit(body, allowed_tenant: str) -> dict | None:
    if not isinstance(body, dict) or body.get("content_access") != "HANDLES_ONLY":
        return None
    if _PRIVATE.intersection(body):
        return None
    if body.get("execution_authority") not in (None, "NONE") or body.get("execution_authorized") not in (None, False):
        return _held("DENIED", "AUTHORITY_PROMOTION", "REFUSE")
    if isinstance(body.get("state"), (list, dict)):
        return _held("DENIED", "MALFORMED", "REFUSE")
    if body.get("state") in {"UNCERTAIN", "INDETERMINATE"}:
        return {
            "state": "UNCERTAIN",
            "action": "ABSTAIN",
            "handles": [],
            "evidence": [],
            "hydrated": False,
            "content_access": "HANDLES_ONLY",
            "reason": "UNCERTAIN",
            "source_revision": None,
            "upstream_state": body.get("state"),
        }
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
    hold = None
    for item in evidence:
        if not isinstance(item, dict) or _PRIVATE.intersection(item):
            return None
        node = item.get("node_id")
        source = item.get("source")
        digest = item.get("sha256")
        if (
            not isinstance(node, str)
            or not isinstance(source, str)
            or not source
            or len(source) > 256
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            return None
        rights = item.get("rights")
        tenant = item.get("tenant")
        if rights in _RIGHTS_WITHDRAWN:
            hold = hold or "withdrawn"
            continue
        if isinstance(tenant, str) and tenant != allowed_tenant:
            hold = "wrong_tenant"
            continue
        if not _bound_row(item, allowed_tenant):
            hold = hold or "unbound"
            continue
        evidence_ids.append(node)
        clean_evidence.append({
            "node_id": node,
            "source": source,
            "sha256": digest,
            "document_revision": item["document_revision"],
            "license": item["license"],
            "rights": rights,
            "tenant": tenant,
        })
    if hold == "wrong_tenant":
        return _held("DENIED", "WRONG_TENANT", "REFUSE")
    if hold == "withdrawn":
        return _held("ABSTAIN", "WITHDRAWN", "ABSTAIN")
    if hold:
        return _held("ABSTAIN", "RIGHTS_UNBOUND", "ABSTAIN")
    if set(handle_ids) != set(evidence_ids):
        return None
    state = body.get("state")
    if state == "GROUNDED_HANDLES_READY":
        reported = "AVAILABLE"
    elif isinstance(state, str) and state.startswith("ABSTAIN") and _UPSTREAM.fullmatch(state) is not None:
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
        "execution_authority": "NONE",
        "tenant": allowed_tenant,
    }
