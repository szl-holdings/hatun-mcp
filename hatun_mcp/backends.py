"""
hatun_mcp.backends — REAL HTTP clients to the live SZL flagship Spaces.

No mocks. Each function calls the documented live endpoint. If a route is not yet
deployed (e.g. WAYRA, or a flagship route still in-flight), the call returns an
HONEST structured payload {"deployed": false, "reason": ...} captured from the real
HTTP status — disclosed in the Khipu receipt, never faked.

Live base URLs (re-verified 2026-06-16). The immune/companion/llm organs (which
replaced the PURGED sentra/rosie/amaru backends) are served by the live a11oy
platform on a-11-oy.com:
  a11oy       https://a-11-oy.com           (immune / companion / llm / policy / router)
  killinchu   https://szlholdings-killinchu.hf.space
  lean-kernel https://szlholdings-lean-kernel.hf.space
  anatomy-3d  https://szlholdings-anatomy-3d.hf.space

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

# The a11oy platform now serves the immune/companion/llm organs directly, so they
# all point at the same live base. SZL_A11OY_URL overrides all three at once.
_A11OY = os.environ.get("SZL_A11OY_URL", "https://a-11-oy.com")
BASES = {
    "a11oy": _A11OY,
    "llm": os.environ.get("SZL_LLM_URL", _A11OY),
    "immune": os.environ.get("SZL_IMMUNE_URL", _A11OY),
    "killinchu": os.environ.get("SZL_KILLINCHU_URL", "https://szlholdings-killinchu.hf.space"),
    "companion": os.environ.get("SZL_COMPANION_URL", _A11OY),
    "lean": os.environ.get("SZL_LEAN_URL", "https://szlholdings-lean-kernel.hf.space"),
    "anatomy": os.environ.get("SZL_ANATOMY_URL", "https://szlholdings-anatomy-3d.hf.space"),
    "second_brain": os.environ.get("SZL_SECOND_BRAIN_URL", "https://szlholdings-szl-second-brain.hf.space"),
}

DEFAULT_TIMEOUT = float(os.environ.get("HATUN_MCP_BACKEND_TIMEOUT", "5.0"))

# The estate observer is intentionally not configurable.  It is a public,
# read-only evidence surface for the one organization this server represents,
# not a general-purpose URL fetcher or a way to reuse a privileged GitHub token.
GITHUB_ESTATE_ORIGIN = "https://api.github.com"
GITHUB_ESTATE_ORG = "szl-holdings"
GITHUB_ESTATE_SCHEMA = "szl.hatun.github-estate-snapshot/v1"
GITHUB_ESTATE_TIMEOUT_S = 15.0
GITHUB_ESTATE_MAX_REPO_PAGES = 3
GITHUB_ESTATE_MAX_REPOSITORIES = 300
GITHUB_ESTATE_MAX_OPEN_PRS = 50
GITHUB_ESTATE_MAX_CHECK_RUNS_PER_PR = 100
GITHUB_ESTATE_MAX_REQUESTS = 20
GITHUB_ESTATE_MAX_RESPONSE_BYTES = 1_048_576
GITHUB_ESTATE_MAX_TOTAL_RESPONSE_BYTES = 4_194_304

_LOWER_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_GITHUB_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_GITHUB_LINK_REL_RE = re.compile(r'(?:^|;)\s*rel\s*=\s*(?:"([^"]*)"|([^;,\s]+))', re.I)
_REPOSITORY_NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
_ALLOWED_GITHUB_PATHS = (
    re.compile(r"/orgs/szl-holdings/repos\Z"),
    re.compile(r"/search/issues\Z"),
    re.compile(r"/repos/szl-holdings/[A-Za-z0-9_.-]{1,100}/pulls/[1-9][0-9]*\Z"),
    re.compile(
        r"/repos/szl-holdings/[A-Za-z0-9_.-]{1,100}/commits/"
        r"[0-9a-f]{40}/check-runs\Z"
    ),
)


class BackendResult(dict):
    """Dict subclass with .ok convenience."""

    @property
    def ok(self) -> bool:
        return bool(self.get("deployed", True)) and self.get("error") is None


class _GithubObservationError(Exception):
    """Sanitized provider failure.  Provider bodies and exception text stay out."""

    def __init__(self, code: str, http_status: Optional[int] = None) -> None:
        super().__init__(code)
        self.code = code
        self.http_status = http_status


def _github_observed_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _github_canonical_digest(snapshot_without_evidence: dict) -> str:
    payload = json.dumps(
        snapshot_without_evidence,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _github_path_allowed(path: str) -> bool:
    return not any(part in (".", "..") for part in path.split("/")) and any(
        pattern.fullmatch(path) for pattern in _ALLOWED_GITHUB_PATHS
    )


def _github_branch_valid(value: Any) -> bool:
    """Validate a displayed branch name, never an input to a request URL."""
    if not isinstance(value, str) or not 1 <= len(value) <= 1024:
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    if value == "@" or value.startswith(("/", "-")) or value.endswith(("/", ".")):
        return False
    if any(part in value for part in ("..", "@{", "//")):
        return False
    if any(ord(char) < 33 or ord(char) == 127 or char in "~^:?*[\\" for char in value):
        return False
    return all(
        not part.startswith(".") and not part.endswith(".lock")
        for part in value.split("/")
    )


def _github_timestamp_valid(value: Any) -> bool:
    if not isinstance(value, str) or not _GITHUB_TIMESTAMP_RE.fullmatch(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _github_json_constant_rejected(value: str) -> None:
    raise ValueError("NONFINITE_JSON_NUMBER")


async def _github_read_json(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: Optional[dict] = None,
    byte_budget: Optional[dict] = None,
) -> tuple[Any, dict, bool]:
    """Bound accepted body bytes, not transport prefetch or rejected chunks.

    All callers share an exhaustion latch. Checks and counter updates contain
    no awaits, so one observer cannot accept bytes after another exhausts the
    budget. Already-running transport reads may return one rejected chunk;
    lower-level buffering and wire traffic are deliberately not measured.
    """
    def check_total_budget() -> None:
        if byte_budget is not None and (
            byte_budget["exhausted"]
            or byte_budget["accepted"] >= GITHUB_ESTATE_MAX_TOTAL_RESPONSE_BYTES
        ):
            byte_budget["exhausted"] = True
            raise _GithubObservationError("TOTAL_RESPONSE_BYTES_LIMIT")

    if not _github_path_allowed(path):
        raise _GithubObservationError("PATH_NOT_ALLOWLISTED")

    request = client.build_request("GET", path, params=params or {})
    if (
        request.url.scheme != "https"
        or request.url.host != "api.github.com"
        or request.url.port not in (None, 443)
        or request.url.username
        or request.url.password
        or request.url.path != path
    ):
        raise _GithubObservationError("ORIGIN_NOT_ALLOWLISTED")

    check_total_budget()
    try:
        response = await client.send(request, stream=True, follow_redirects=False)
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise _GithubObservationError(
            f"TRANSPORT_{type(exc).__name__.upper()}"
        ) from None

    try:
        check_total_budget()
        status = response.status_code
        if 300 <= status < 400:
            raise _GithubObservationError("REDIRECT_REJECTED", status)
        if status == 429 or (
            status == 403 and (
                response.headers.get("x-ratelimit-remaining") == "0"
                or "retry-after" in response.headers
            )
        ):
            raise _GithubObservationError("RATE_LIMITED", status)
        if status != 200:
            raise _GithubObservationError(f"HTTP_{status}", status)
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise _GithubObservationError("COMPRESSED_RESPONSE_REJECTED", status)

        declared_length = response.headers.get("content-length")
        if declared_length:
            try:
                length = int(declared_length)
                if length < 0:
                    raise _GithubObservationError("INVALID_CONTENT_LENGTH", status)
                if length > GITHUB_ESTATE_MAX_RESPONSE_BYTES:
                    raise _GithubObservationError("RESPONSE_TOO_LARGE", status)
                if byte_budget is not None and (
                    length > GITHUB_ESTATE_MAX_TOTAL_RESPONSE_BYTES - byte_budget["accepted"]
                ):
                    byte_budget["exhausted"] = True
                    raise _GithubObservationError("TOTAL_RESPONSE_BYTES_LIMIT", status)
            except ValueError:
                raise _GithubObservationError("INVALID_CONTENT_LENGTH", status) from None

        chunks: list[bytes] = []
        accepted_bytes = 0
        # Do not use the chunk-size adapter: it can await multiple underlying
        # reads before yielding, bypassing the shared latch between reads.
        iterator = response.aiter_bytes().__aiter__()
        while True:
            check_total_budget()
            try:
                chunk = await iterator.__anext__()
            except StopAsyncIteration:
                break
            check_total_budget()
            if accepted_bytes + len(chunk) > GITHUB_ESTATE_MAX_RESPONSE_BYTES:
                raise _GithubObservationError("RESPONSE_TOO_LARGE", status)
            if byte_budget is not None:
                if len(chunk) > GITHUB_ESTATE_MAX_TOTAL_RESPONSE_BYTES - byte_budget["accepted"]:
                    byte_budget["exhausted"] = True
                    raise _GithubObservationError("TOTAL_RESPONSE_BYTES_LIMIT", status)
                byte_budget["accepted"] += len(chunk)
            accepted_bytes += len(chunk)
            chunks.append(chunk)
        response_bytes = b"".join(chunks)
        try:
            body = json.loads(response_bytes, parse_constant=_github_json_constant_rejected)
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise _GithubObservationError("INVALID_JSON", status) from None

        citation = {
            "provider": "github",
            "method": "GET",
            "origin": GITHUB_ESTATE_ORIGIN,
            "path": path,
            "params": dict(sorted(request.url.params.multi_items())),
            "status": status,
            "response_bytes": accepted_bytes,
            "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
        }
        link = response.headers.get("link", "")
        relations = _GITHUB_LINK_REL_RE.findall(link)
        if link and not relations:
            raise _GithubObservationError("INVALID_PAGINATION_LINK", status)
        has_next = any(
            "next" in (quoted or unquoted).lower().split()
            for quoted, unquoted in relations
        )
        return body, citation, has_next
    finally:
        await response.aclose()


def _normalize_github_repository(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise _GithubObservationError("INVALID_REPOSITORY_RECORD")
    owner = raw.get("owner")
    if not isinstance(owner, dict) or owner.get("login") != GITHUB_ESTATE_ORG:
        raise _GithubObservationError("OWNER_MISMATCH")
    name = raw.get("name")
    full_name = raw.get("full_name")
    if (
        not isinstance(name, str)
        or not _REPOSITORY_NAME_RE.fullmatch(name)
        or name in (".", "..")
    ):
        raise _GithubObservationError("INVALID_REPOSITORY_NAME")
    if full_name != f"{GITHUB_ESTATE_ORG}/{name}":
        raise _GithubObservationError("REPOSITORY_ID_MISMATCH")
    if raw.get("private") is not False:
        raise _GithubObservationError("NON_PUBLIC_REPOSITORY_RETURNED")
    default_branch = raw.get("default_branch")
    if default_branch is not None and not _github_branch_valid(default_branch):
        raise _GithubObservationError("INVALID_DEFAULT_BRANCH")
    for flag in ("archived", "disabled", "fork"):
        if type(raw.get(flag)) is not bool:
            raise _GithubObservationError("INVALID_REPOSITORY_FLAG")
    return {
        "name": name,
        "name_with_owner": full_name,
        "visibility": "PUBLIC",
        "archived": raw["archived"],
        "disabled": raw["disabled"],
        "fork": raw["fork"],
        "default_branch": {
            "name": default_branch,
            "head_sha": None,
            "state": "NAMED_NOT_RESOLVED" if default_branch else "UNAVAILABLE",
        },
        "pushed_at": raw.get("pushed_at") if _github_timestamp_valid(raw.get("pushed_at")) else None,
        "updated_at": raw.get("updated_at") if _github_timestamp_valid(raw.get("updated_at")) else None,
        "web_url": f"https://github.com/{full_name}",
    }


def _github_check_rollup(raw: Any, expected_head_sha: str) -> dict:
    if not isinstance(expected_head_sha, str) or not _LOWER_SHA_RE.fullmatch(expected_head_sha):
        raise _GithubObservationError("INVALID_EXPECTED_CHECK_HEAD")
    if not isinstance(raw, dict) or not isinstance(raw.get("check_runs"), list):
        raise _GithubObservationError("INVALID_CHECK_RUNS_RESPONSE")
    runs = raw["check_runs"]
    total = raw.get("total_count")
    if type(total) is not int or total < 0:
        raise _GithubObservationError("INVALID_CHECK_RUN_COUNT")
    if total != len(runs) or total > GITHUB_ESTATE_MAX_CHECK_RUNS_PER_PR:
        raise _GithubObservationError("CHECK_RUNS_INCOMPLETE")

    counts = {
        "total": total,
        "completed": 0,
        "in_progress": 0,
        "queued": 0,
        "success": 0,
        "neutral": 0,
        "skipped": 0,
        "failure": 0,
        "cancelled": 0,
        "timed_out": 0,
        "action_required": 0,
        "other": 0,
    }
    seen_ids: set[int] = set()
    for run in runs:
        if not isinstance(run, dict):
            raise _GithubObservationError("INVALID_CHECK_RUN")
        run_id = run.get("id")
        if type(run_id) is not int or run_id < 1:
            raise _GithubObservationError("INVALID_CHECK_RUN_ID")
        if run_id in seen_ids:
            raise _GithubObservationError("DUPLICATE_CHECK_RUN")
        seen_ids.add(run_id)
        if run.get("head_sha") != expected_head_sha:
            raise _GithubObservationError("CHECK_HEAD_MISMATCH")
        status = run.get("status")
        conclusion = run.get("conclusion")
        if status in ("completed", "in_progress", "queued"):
            counts[status] += 1
        else:
            counts["other"] += 1
        if status == "completed":
            if conclusion in (
                "success",
                "neutral",
                "skipped",
                "failure",
                "cancelled",
                "timed_out",
                "action_required",
            ):
                counts[conclusion] += 1
            else:
                counts["other"] += 1
        elif conclusion is not None:
            counts["other"] += 1
    terminal_failures = sum(
        counts[key]
        for key in ("failure", "cancelled", "timed_out", "action_required")
    )
    complete = total > 0 and counts["other"] == 0
    if terminal_failures:
        state = "FAILURE"
    elif not complete:
        state = "UNKNOWN"
    elif counts["in_progress"] or counts["queued"]:
        state = "IN_PROGRESS"
    elif total == counts["success"]:
        state = "SUCCESS"
    elif total == counts["completed"]:
        state = "NEUTRAL"
    else:
        state = "UNKNOWN"
    return {"state": state, "counts": counts, "complete": complete}


async def github_estate_snapshot(*, signer_mode: str) -> BackendResult:
    """Observe the fixed public GitHub estate without accepting URLs or tokens.

    The result is complete only inside its explicitly public structural scope.
    Private repositories, deployments, model evidence, branch protection and
    default-branch head SHAs are intentionally not inferred.
    """
    observed_at = _github_observed_at()
    repositories: list[dict] = []
    pull_requests: list[dict] = []
    citations: list[dict] = []
    gaps: list[str] = []
    request_count = 0
    byte_budget = {"accepted": 0, "exhausted": False}
    repo_pagination_exhausted = False
    pr_inventory_observed = False
    open_pr_count: Optional[int] = None

    async def get_json(path: str, *, params: Optional[dict] = None):
        nonlocal request_count
        if byte_budget["exhausted"] or byte_budget["accepted"] >= GITHUB_ESTATE_MAX_TOTAL_RESPONSE_BYTES:
            byte_budget["exhausted"] = True
            raise _GithubObservationError("TOTAL_RESPONSE_BYTES_LIMIT")
        if request_count >= GITHUB_ESTATE_MAX_REQUESTS:
            raise _GithubObservationError("REQUEST_LIMIT")
        request_count += 1
        body, citation, has_next = await _github_read_json(
            client, path, params=params, byte_budget=byte_budget
        )
        citations.append(citation)
        return body, has_next

    async def collect() -> None:
        nonlocal repo_pagination_exhausted, pr_inventory_observed, open_pr_count
        seen_repositories: set[str] = set()
        for page in range(1, GITHUB_ESTATE_MAX_REPO_PAGES + 1):
            body, has_next = await get_json(
                f"/orgs/{GITHUB_ESTATE_ORG}/repos",
                params={
                    "type": "public",
                    "sort": "full_name",
                    "direction": "asc",
                    "per_page": 100,
                    "page": page,
                },
            )
            if not isinstance(body, list):
                raise _GithubObservationError("INVALID_REPOSITORY_RESPONSE")
            if len(body) > 100:
                raise _GithubObservationError("REPOSITORY_PAGE_LIMIT")
            for raw in body:
                normalized = _normalize_github_repository(raw)
                key = normalized["name_with_owner"].casefold()
                if key in seen_repositories:
                    raise _GithubObservationError("DUPLICATE_REPOSITORY")
                if len(repositories) >= GITHUB_ESTATE_MAX_REPOSITORIES:
                    raise _GithubObservationError("REPOSITORY_LIMIT")
                seen_repositories.add(key)
                repositories.append(normalized)
            if not has_next:
                repo_pagination_exhausted = True
                break
        if not repo_pagination_exhausted:
            raise _GithubObservationError("REPOSITORY_PAGINATION_LIMIT")

        search, search_has_next = await get_json(
            "/search/issues",
            params={
                "q": f"org:{GITHUB_ESTATE_ORG} is:pr is:open is:public",
                "sort": "updated",
                "order": "desc",
                "per_page": GITHUB_ESTATE_MAX_OPEN_PRS,
                "page": 1,
            },
        )
        if not isinstance(search, dict) or not isinstance(search.get("items"), list):
            raise _GithubObservationError("INVALID_PULL_REQUEST_SEARCH")
        total_open = search.get("total_count")
        if type(total_open) is not int or total_open < 0:
            raise _GithubObservationError("INVALID_PULL_REQUEST_COUNT")
        open_pr_count = total_open
        if search.get("incomplete_results") is not False:
            raise _GithubObservationError("PULL_REQUEST_SEARCH_INCOMPLETE")
        if (
            total_open != len(search["items"])
            or total_open > GITHUB_ESTATE_MAX_OPEN_PRS
            or search_has_next
        ):
            raise _GithubObservationError("PULL_REQUEST_LIMIT")
        pr_inventory_observed = True

        semaphore = asyncio.Semaphore(4)
        seen_pull_requests: set[tuple[str, int]] = set()

        async def observe_pull_request(item: Any) -> dict:
            if not isinstance(item, dict):
                raise _GithubObservationError("INVALID_PULL_REQUEST_RECORD")
            repository_url = item.get("repository_url")
            prefix = f"{GITHUB_ESTATE_ORIGIN}/repos/{GITHUB_ESTATE_ORG}/"
            if not isinstance(repository_url, str) or not repository_url.startswith(prefix):
                raise _GithubObservationError("PULL_REQUEST_OWNER_MISMATCH")
            repository = repository_url[len(prefix) :]
            if not _REPOSITORY_NAME_RE.fullmatch(repository) or repository in (".", ".."):
                raise _GithubObservationError("INVALID_PULL_REQUEST_REPOSITORY")
            if f"{GITHUB_ESTATE_ORG}/{repository}".casefold() not in seen_repositories:
                raise _GithubObservationError("PULL_REQUEST_REPOSITORY_UNOBSERVED")
            number = item.get("number")
            if type(number) is not int or number < 1:
                raise _GithubObservationError("INVALID_PULL_REQUEST_NUMBER")
            key = (repository.casefold(), number)
            if key in seen_pull_requests:
                raise _GithubObservationError("DUPLICATE_PULL_REQUEST")
            seen_pull_requests.add(key)
            detail_path = f"/repos/{GITHUB_ESTATE_ORG}/{repository}/pulls/{number}"
            if item.get("state") != "open":
                raise _GithubObservationError("PULL_REQUEST_SEARCH_NOT_OPEN")
            search_pr = item.get("pull_request")
            if (
                not isinstance(search_pr, dict)
                or search_pr.get("url") != GITHUB_ESTATE_ORIGIN + detail_path
            ):
                raise _GithubObservationError("INVALID_PULL_REQUEST_SEARCH_IDENTITY")

            detail, _ = await get_json(detail_path)
            if not isinstance(detail, dict):
                raise _GithubObservationError("INVALID_PULL_REQUEST_DETAIL")
            if type(detail.get("number")) is not int or detail["number"] != number:
                raise _GithubObservationError("PULL_REQUEST_NUMBER_MISMATCH")
            if detail.get("state") != "open" or detail.get("merged") is not False:
                raise _GithubObservationError("PULL_REQUEST_NO_LONGER_OPEN")
            if type(detail.get("draft")) is not bool:
                raise _GithubObservationError("INVALID_PULL_REQUEST_DRAFT")
            if (
                not _github_timestamp_valid(item.get("updated_at"))
                or detail.get("updated_at") != item["updated_at"]
            ):
                raise _GithubObservationError("PULL_REQUEST_SEARCH_STALE")
            base = detail.get("base")
            head = detail.get("head")
            if not isinstance(base, dict) or not isinstance(head, dict):
                raise _GithubObservationError("INVALID_PULL_REQUEST_REFS")
            base_repo = base.get("repo")
            if (
                not isinstance(base_repo, dict)
                or base_repo.get("full_name") != f"{GITHUB_ESTATE_ORG}/{repository}"
                or not isinstance(base_repo.get("owner"), dict)
                or base_repo["owner"].get("login") != GITHUB_ESTATE_ORG
                or base_repo.get("private") is not False
            ):
                raise _GithubObservationError("PULL_REQUEST_BASE_MISMATCH")
            base_sha = base.get("sha")
            head_sha = head.get("sha")
            if not isinstance(base_sha, str) or not _LOWER_SHA_RE.fullmatch(base_sha):
                raise _GithubObservationError("INVALID_BASE_SHA")
            if not isinstance(head_sha, str) or not _LOWER_SHA_RE.fullmatch(head_sha):
                raise _GithubObservationError("INVALID_HEAD_SHA")
            if not _github_branch_valid(base.get("ref")) or not _github_branch_valid(head.get("ref")):
                raise _GithubObservationError("INVALID_PULL_REQUEST_BRANCH")

            checks, checks_has_next = await get_json(
                f"/repos/{GITHUB_ESTATE_ORG}/{repository}/commits/"
                f"{head_sha}/check-runs",
                params={"per_page": GITHUB_ESTATE_MAX_CHECK_RUNS_PER_PR, "page": 1},
            )
            if checks_has_next:
                raise _GithubObservationError("CHECK_RUNS_INCOMPLETE")
            rollup = _github_check_rollup(checks, head_sha)
            if not rollup["complete"]:
                gaps.append("CHECK_RUNS_UNASSESSED")
            result = {
                "repository": f"{GITHUB_ESTATE_ORG}/{repository}",
                "number": number,
                "state": "open",
                "draft": detail["draft"],
                "base": {"ref": base.get("ref"), "sha": base_sha},
                "head": {"ref": head.get("ref"), "sha": head_sha},
                "mergeable_state": detail.get("mergeable_state")
                if detail.get("mergeable_state") in (
                    "behind", "blocked", "clean", "dirty", "draft",
                    "has_hooks", "unknown", "unstable",
                )
                else None,
                "checks": rollup,
                "updated_at": detail.get("updated_at")
                if isinstance(detail.get("updated_at"), str)
                else None,
                "web_url": f"https://github.com/{GITHUB_ESTATE_ORG}/{repository}/pull/{number}",
            }
            pull_requests.append(result)
            return result

        async def bounded_pr_observation(item: Any) -> dict:
            # Hold a slot across detail AND checks. Otherwise queued detail
            # requests can consume the entire budget before any check read.
            async with semaphore:
                return await observe_pull_request(item)

        results = await asyncio.gather(
            *(bounded_pr_observation(item) for item in search["items"]),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, _GithubObservationError):
                gaps.append(result.code)
            elif isinstance(result, asyncio.CancelledError):
                # A child cancellation is returned by gather, not raised. It is
                # BaseException, so an Exception-only check silently loses a PR.
                gaps.append("PULL_REQUEST_OBSERVATION_CANCELLED")
            elif isinstance(result, Exception):
                gaps.append(f"UNEXPECTED_{type(result).__name__.upper()}")
        if len(pull_requests) != total_open:
            gaps.append("PULL_REQUEST_DETAIL_COVERAGE_INCOMPLETE")

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "szl-hatun-estate-observer/1.0",
        "Accept-Encoding": "identity",
    }
    timeout = httpx.Timeout(connect=2.0, read=4.0, write=2.0, pool=1.0)
    limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
    async with httpx.AsyncClient(
        base_url=GITHUB_ESTATE_ORIGIN,
        headers=headers,
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        try:
            await asyncio.wait_for(collect(), timeout=GITHUB_ESTATE_TIMEOUT_S)
        except asyncio.TimeoutError:
            gaps.append("OVERALL_TIMEOUT")
        except _GithubObservationError as exc:
            gaps.append(exc.code)
        except Exception as exc:
            gaps.append(f"UNEXPECTED_{type(exc).__name__.upper()}")

    gaps = sorted(set(gaps))
    usable = bool(repositories) or pr_inventory_observed
    state = "COMPLETE" if not gaps else ("INCOMPLETE" if usable else "UNAVAILABLE")
    repositories.sort(key=lambda item: item["name_with_owner"].casefold())
    pull_requests.sort(key=lambda item: (item["repository"].casefold(), item["number"]))
    citations.sort(key=lambda item: (item["path"], tuple(item["params"].items())))

    snapshot = {
        "schema": GITHUB_ESTATE_SCHEMA,
        "state": state,
        "observed_at": observed_at,
        "target": {
            "github_org": GITHUB_ESTATE_ORG,
            "scope": "PUBLIC_ONLY",
        },
        "effects": {
            "provider_access": "READ_ONLY",
            "provider_methods": ["GET"],
            "provider_remote_writes": 0,
        },
        "coverage": {
            "complete_within_public_scope": state == "COMPLETE",
            "repository_pagination_exhausted": repo_pagination_exhausted,
            "open_pull_request_inventory_observed": pr_inventory_observed,
            "consistency": "BEST_EFFORT_MULTI_REQUEST_NOT_ATOMIC",
            "gaps": gaps,
            "not_attested": [
                "BRANCH_PROTECTION",
                "DEFAULT_BRANCH_HEAD_SHAS",
                "DEPLOYMENT_RUNTIME",
                "MODEL_TRAINING_OR_EVALUATION",
                "PRIVATE_REPOSITORIES",
                "REQUIRED_CHECKS_AND_MERGE_ELIGIBILITY",
                "LEGACY_COMMIT_STATUS_CONTEXTS",
                "REVIEW_APPROVALS",
            ],
        },
        "limits": {
            "repository_pages": GITHUB_ESTATE_MAX_REPO_PAGES,
            "repositories": GITHUB_ESTATE_MAX_REPOSITORIES,
            "open_pull_requests": GITHUB_ESTATE_MAX_OPEN_PRS,
            "check_runs_per_pull_request": GITHUB_ESTATE_MAX_CHECK_RUNS_PER_PR,
            "requests": GITHUB_ESTATE_MAX_REQUESTS,
            "response_body_bytes_accepted_per_response": GITHUB_ESTATE_MAX_RESPONSE_BYTES,
            "response_body_bytes_accepted_total": GITHUB_ESTATE_MAX_TOTAL_RESPONSE_BYTES,
            "response_body_accounting": "ACCEPTED_APPLICATION_BYTES_TRANSPORT_PREFETCH_NOT_MEASURED",
            "wall_clock_seconds": GITHUB_ESTATE_TIMEOUT_S,
        },
        "counts": {
            "repositories_observed": len(repositories),
            "active_repositories_observed": sum(
                not item["archived"] for item in repositories
            ),
            "archived_repositories_observed": sum(
                item["archived"] for item in repositories
            ),
            "open_pull_requests_observed": len(pull_requests),
            "open_pull_requests_reported_by_search": open_pr_count,
            "requests_issued": request_count,
            "response_body_bytes_accepted": byte_budget["accepted"],
        },
        "repositories": repositories,
        "open_pull_requests": pull_requests,
        "citations": citations,
        "cryptographic_attestation": {
            "state": "NOT_SIGNED_BY_OBSERVER",
            "envelope_signer_mode": "ECDSA-P256" if signer_mode == "ECDSA-P256" else "UNSIGNED",
            "signature_location": "GOVERNED_TOOL_ENVELOPE_IF_SIGNED",
            "admissible_for_mutation": False,
        },
    }
    digest = _github_canonical_digest(snapshot)
    snapshot["evidence"] = {
        "algorithm": "sha256",
        "canonicalization": "JSON_SORT_KEYS_COMPACT_UTF8_V1",
        "payload_scope": "snapshot_without_evidence",
        "digest": digest,
    }
    complete = state == "COMPLETE"
    return BackendResult(
        deployed=complete,
        http_status=200 if complete else None,
        endpoint=f"{GITHUB_ESTATE_ORIGIN}/orgs/{GITHUB_ESTATE_ORG}/repos",
        error=None if complete else f"github_estate_{state.lower()}",
        reason=None if complete else ",".join(gaps),
        evidence_state=state,
        evidence_schema=GITHUB_ESTATE_SCHEMA,
        evidence_digest_sha256=digest,
        data=snapshot,
    )


async def _post(flagship: str, paths: list[str], payload: dict,
                timeout: float = DEFAULT_TIMEOUT) -> BackendResult:
    """POST to the first path that exists; fall back across candidate routes.
    Returns an honest result indicating real HTTP status. Never raises to the tool."""
    base = BASES[flagship]
    last_status = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for p in paths:
            url = base + p
            try:
                r = await client.post(url, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_status = f"transport_error:{type(e).__name__}"
                continue
            last_status = r.status_code
            if r.status_code == 404:
                continue  # try next candidate route
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text[:2000]}
            return BackendResult(
                deployed=True, http_status=r.status_code, endpoint=url,
                error=None if r.status_code < 400 else f"http_{r.status_code}",
                data=body,
            )
    return BackendResult(
        deployed=False, http_status=last_status, endpoint=base + paths[0],
        error="route_not_live",
        reason=(f"No candidate route live yet (last status {last_status}). "
                "Honest stub — disclosed, not faked."),
        data=None,
    )


async def _get(flagship: str, paths: list[str], params: Optional[dict] = None,
               timeout: float = DEFAULT_TIMEOUT) -> BackendResult:
    base = BASES[flagship]
    last_status = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for p in paths:
            url = base + p
            try:
                r = await client.get(url, params=params or {})
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_status = f"transport_error:{type(e).__name__}"
                continue
            last_status = r.status_code
            if r.status_code == 404:
                continue
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text[:2000]}
            return BackendResult(
                deployed=True, http_status=r.status_code, endpoint=url,
                error=None if r.status_code < 400 else f"http_{r.status_code}",
                data=body,
            )
    return BackendResult(
        deployed=False, http_status=last_status, endpoint=base + paths[0],
        error="route_not_live",
        reason=(f"No candidate route live yet (last status {last_status}). "
                "Honest stub — disclosed, not faked."),
        data=None,
    )


# ── Per-flagship typed wrappers (documented real routes + fallbacks) ────────────

async def a11oy_router(messages: list, model: Optional[str] = None,
                       sovereign: bool = False) -> BackendResult:
    payload = {
        "organ": "a11oy", "task_class": "general", "modality": "text",
        "context_tokens": 0,
        "governance_tier": "sovereign" if sovereign else "standard",
        "messages": messages,
    }
    if model:
        payload["model"] = model
    return await _post("a11oy", ["/v1/router", "/api/a11oy/v1/llm/route"], payload)


async def a11oy_policy_evaluate(action: dict, context: dict) -> BackendResult:
    return await _post("a11oy", ["/api/a11oy/v1/policy/evaluate", "/v1/policy/evaluate"],
                       {"action": action, "context": context})


async def killinchu_identify(signature: dict) -> BackendResult:
    return await _post("killinchu", ["/counter-uas/identify", "/v1/iff"], signature)


async def killinchu_cue(track: dict, asset_value_polygon: dict) -> BackendResult:
    return await _post("killinchu", ["/v1/cue", "/cue"],
                       {"track": track, "asset_value_polygon": asset_value_polygon})


async def killinchu_predict_impact(track_id: str, horizon_seconds: int) -> BackendResult:
    return await _post("killinchu", ["/v1/predict-impact"],
                       {"track_id": track_id, "horizon_seconds": horizon_seconds})


async def killinchu_drones(model_or_signature: str) -> BackendResult:
    return await _get("killinchu", ["/v1/drones"], params={"q": model_or_signature})


async def immune_screen(target: dict) -> BackendResult:
    """Immune screen of an action (code / SBOM / image). The a11oy immune organ has
    no separate /screen route — the screen IS the signed verdict route (live 200)."""
    return await _post("immune", ["/api/a11oy/v1/immune/verdict"],
                       {"action": target, "context": {}})


async def companion_ask(question: str, context: Any) -> BackendResult:
    """Ask the a11oy companion to reason. Live route POST /api/a11oy/v1/companion/ask
    (answers only from live platform data; refuses to fabricate)."""
    return await _post("companion", ["/api/a11oy/v1/companion/ask"],
                       {"question": question, "context": context})


async def companion_rag(question: str) -> BackendResult:
    """Grounded RAG-style query routed through the a11oy companion /ask endpoint."""
    return await _post("companion", ["/api/a11oy/v1/companion/ask"],
                       {"question": question, "topic": "doctrine",
                        "corpus": "thesis-corpus-v18"})


async def khipu_verify(flagship: str, receipt_hash: str,
                       merkle_proof: Optional[list] = None) -> BackendResult:
    fl = flagship if flagship in BASES else "a11oy"
    return await _post(fl, ["/khipu/verify", "/api/a11oy/v1/khipu/verify"],
                       {"receipt_hash": receipt_hash, "merkle_proof": merkle_proof or []})


async def lean_verify(theorem_name: str) -> BackendResult:
    return await _post("lean", ["/lean-verify"], {"theorem": theorem_name})


def anatomy_scene_url(organ: str, animation_state: str = "idle") -> str:
    base = BASES["anatomy"]
    return f"{base}/?organ={organ}&state={animation_state}&src=hatun-mcp"


# ── Formula evaluation (REAL deterministic math; falls back to lean kernel) ──────
# A small library of doctrine formula primitives, evaluated with real arithmetic.
# No mocks: each is a closed-form computation. Unknown names are forwarded to the
# live lean kernel's /formula-eval route; if that route is not live the honest
# 'route_not_live' result is returned and disclosed in the Khipu receipt.
import math as _math


def _eval_known_formula(name: str, args: dict) -> Optional[dict]:
    n = (name or "").strip().lower()
    a = args or {}
    def _f(k, d=0.0):
        try:
            return float(a.get(k, d))
        except (TypeError, ValueError):
            return d
    if n in ("puriq", "puriq_master", "p_x_t", "master"):
        lam = _f("lambda", 1.0); yuyay = _f("yuyay_13", 1.0)
        beta = _f("beta", 8.0); hukla = _f("hukla", 0.0)
        khipu = _f("khipu", 1.0); hatun = _f("hatun_mcp", 1.0)
        val = lam * yuyay * _math.exp(-beta * hukla) * khipu * hatun
        return {"formula": "P(x,t)=\u039b\u00b7Yuyay\u2081\u2083\u00b7exp(-\u03b2\u00b7HUKLLA)\u00b7\u220fKhipu\u00b7Hatun_MCP",
                "inputs": {"lambda": lam, "yuyay_13": yuyay, "beta": beta,
                           "hukla": hukla, "khipu": khipu, "hatun_mcp": hatun},
                "value": val}
    if n in ("kl", "kl_divergence", "kldivergence"):
        p = a.get("p") or []; q = a.get("q") or []
        if p and q and len(p) == len(q):
            kl = sum(pi * _math.log(pi / qi) for pi, qi in zip(p, q) if pi > 0 and qi > 0)
            return {"formula": "D_KL(P||Q)=\u03a3 p_i log(p_i/q_i)", "value": kl,
                    "note": "klDivergence_nonneg axiom holds: value \u2265 0."}
    if n in ("sigmoid", "logistic"):
        x = _f("x"); return {"formula": "\u03c3(x)=1/(1+e^-x)", "value": 1.0 / (1.0 + _math.exp(-x))}
    if n in ("liu_hui_pi", "pi"):
        sides = int(_f("sides", 96))
        val = sides * _math.sin(_math.pi / sides)  # Liu Hui polygon π approximation
        return {"formula": "Liu Hui: n\u00b7sin(\u03c0/n) \u2192 \u03c0", "sides": sides, "value": val}
    return None


async def formula_evaluate(name: str, args: dict) -> BackendResult:
    """Evaluate a named doctrine formula primitive. Local closed-form for known
    primitives (real arithmetic); otherwise forward to the live lean kernel."""
    local = _eval_known_formula(name, args)
    if local is not None:
        return BackendResult(deployed=True, http_status=200,
                             endpoint="(local closed-form evaluator)", error=None,
                             data={"name": name, **local})
    return await _post("lean", ["/formula-eval", "/lean-verify"],
                       {"formula": name, "args": args})
