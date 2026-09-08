"""Hermetic regression tests for the fixed public GitHub observer.

Every provider request uses MockTransport; these tests never contact GitHub.
SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from unittest.mock import patch

import httpx
import pytest

from hatun_mcp import backends as B


HEAD = "a" * 40
BASE = "b" * 40
_ASYNC_CLIENT = httpx.AsyncClient


def _repo(name="hatun-mcp"):
    return {
        "name": name,
        "full_name": f"szl-holdings/{name}",
        "owner": {"login": "szl-holdings"},
        "private": False,
        "archived": False,
        "disabled": False,
        "fork": False,
        "default_branch": "main",
        "html_url": f"https://github.com/szl-holdings/{name}",
    }


def _item(number=7, repository="hatun-mcp"):
    return {
        "number": number,
        "state": "open",
        "updated_at": "2026-09-07T12:00:00Z",
        "repository_url": f"https://api.github.com/repos/szl-holdings/{repository}",
        "pull_request": {"url": f"https://api.github.com/repos/szl-holdings/{repository}/pulls/{number}"},
    }


def _detail(number=7, repository="hatun-mcp"):
    return {
        "number": number,
        "state": "open",
        "updated_at": "2026-09-07T12:00:00Z",
        "merged": False,
        "draft": False,
        "base": {"repo": _repo(repository), "ref": "main", "sha": BASE},
        "head": {"ref": "fix/estate-observer", "sha": HEAD},
        "mergeable_state": "clean",
        "html_url": f"https://github.com/szl-holdings/{repository}/pull/{number}",
    }


def _run(identifier=101, status="completed", conclusion="success"):
    return {"id": identifier, "head_sha": HEAD, "status": status, "conclusion": conclusion}


def _search(items=None):
    items = [_item()] if items is None else items
    return {"total_count": len(items), "incomplete_results": False, "items": items}


def _handler(*, repositories=None, search=None, detail=None, checks=None):
    """Reject unexpected endpoints rather than letting a fixture hide a request."""
    def handle(request):
        if request.url.path == "/orgs/szl-holdings/repos":
            body = [_repo()] if repositories is None else repositories
        elif request.url.path == "/search/issues":
            body = _search() if search is None else search
        elif request.url.path == "/repos/szl-holdings/hatun-mcp/pulls/7":
            body = _detail() if detail is None else detail
        elif request.url.path == f"/repos/szl-holdings/hatun-mcp/commits/{HEAD}/check-runs":
            body = {"total_count": 1, "check_runs": [_run()]} if checks is None else checks
        else:
            raise AssertionError(f"Unexpected fixture endpoint: {request.url.path}")
        return httpx.Response(200, json=body)
    return handle


def _observe(handler=None, *, signer_mode="ECDSA-P256"):
    requests = []
    options = []
    selected = handler or _handler()

    async def transport(request):
        requests.append(request)
        result = selected(request)
        if hasattr(result, "__await__"):
            return await result
        return result

    def factory(**kwargs):
        options.append(kwargs.copy())
        return _ASYNC_CLIENT(**kwargs, transport=httpx.MockTransport(transport))

    with patch.object(B.httpx, "AsyncClient", factory):
        result = asyncio.run(B.github_estate_snapshot(signer_mode=signer_mode))
    return result, requests, options


def _assert_partial(result):
    assert result["data"]["state"] in {"INCOMPLETE", "UNAVAILABLE"}
    assert result.ok is False
    assert result["data"]["coverage"]["complete_within_public_scope"] is False
    assert result["data"]["coverage"]["gaps"]


class TestGithubEstateSnapshot:
    def test_large_pr_queue_preserves_complete_pr_evidence_before_request_cap(self):
        items = [_item(number=n) for n in range(1, 31)]

        async def handle(request):
            await asyncio.sleep(0)  # Exercise interleaved provider responses.
            if request.url.path == "/orgs/szl-holdings/repos":
                return httpx.Response(200, json=[_repo()])
            if request.url.path == "/search/issues":
                return httpx.Response(200, json=_search(items))
            if "/pulls/" in request.url.path:
                number = int(request.url.path.rsplit("/", 1)[1])
                return httpx.Response(200, json=_detail(number=number))
            if request.url.path.endswith("/check-runs"):
                return httpx.Response(200, json={"total_count": 1, "check_runs": [_run()]})
            raise AssertionError("Unexpected fixture endpoint")

        result, requests, _ = _observe(handle)
        _assert_partial(result)
        assert len(requests) == B.GITHUB_ESTATE_MAX_REQUESTS
        assert result["data"]["counts"]["open_pull_requests_reported_by_search"] == 30
        assert result["data"]["counts"]["open_pull_requests_observed"] >= 4
        assert any(request.url.path.endswith("/check-runs") for request in requests)

    def test_cancelled_child_pr_observation_is_not_silently_complete(self):
        normal = _handler()

        def handle(request):
            if request.url.path.endswith("/pulls/7"):
                raise asyncio.CancelledError()
            return normal(request)

        result, requests, _ = _observe(handle)
        _assert_partial(result)
        assert result["data"]["state"] == "INCOMPLETE"
        assert result["data"]["counts"]["open_pull_requests_observed"] == 0
        assert len(requests) == 3
        assert "PULL_REQUEST_OBSERVATION_CANCELLED" in result["data"]["coverage"]["gaps"]
        assert "PULL_REQUEST_DETAIL_COVERAGE_INCOMPLETE" in result["data"]["coverage"]["gaps"]

    def test_caller_cancellation_propagates_and_stops_active_provider_request(self):
        async def exercise():
            started = asyncio.Event()
            cancelled = []

            async def transport(request):
                started.set()
                try:
                    await asyncio.sleep(30)
                finally:
                    cancelled.append(True)

            def factory(**kwargs):
                return _ASYNC_CLIENT(**kwargs, transport=httpx.MockTransport(transport))

            with patch.object(B.httpx, "AsyncClient", factory):
                task = asyncio.create_task(B.github_estate_snapshot(signer_mode="PLACEHOLDER"))
                await asyncio.wait_for(started.wait(), timeout=1)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert cancelled == [True]

        asyncio.run(exercise())

    def test_complete_public_snapshot_uses_only_fixed_get_without_environment_credentials(self, monkeypatch):
        for key in ("GH_TOKEN", "GITHUB_TOKEN", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            monkeypatch.setenv(key, "sensitive-test-value")
        result, requests, options = _observe()
        assert result.ok is True
        assert result["data"]["state"] == "COMPLETE"
        assert result["data"]["target"] == {"github_org": "szl-holdings", "scope": "PUBLIC_ONLY"}
        assert len(requests) == 4
        assert options[0]["trust_env"] is False
        assert options[0]["follow_redirects"] is False
        for request in requests:
            assert request.method == "GET"
            assert request.url.scheme == "https"
            assert request.url.host == "api.github.com"
            assert "authorization" not in request.headers
            assert "proxy-authorization" not in request.headers
            assert request.content == b""
        assert "sensitive-test-value" not in json.dumps(result)
        assert result["data"]["open_pull_requests"][0]["head"]["sha"] == HEAD
        assert result["data"]["open_pull_requests"][0]["checks"]["state"] == "SUCCESS"
        assert result["data"]["repositories"][0]["default_branch"]["head_sha"] is None
        assert result["data"]["effects"]["provider_remote_writes"] == 0


    def test_empty_public_estate_is_complete_but_does_not_infer_private_coverage(self):
        result, requests, _ = _observe(_handler(repositories=[], search=_search([])))
        assert result["data"]["state"] == "COMPLETE"
        assert len(requests) == 2
        assert "PRIVATE_REPOSITORIES" in result["data"]["coverage"]["not_attested"]


    @pytest.mark.parametrize("status", [301, 302, 307, 308])
    def test_redirects_are_never_followed(self, status):
        result, requests, _ = _observe(lambda _: httpx.Response(status, headers={"location": "https://attacker.invalid/secret"}))
        _assert_partial(result)
        assert len(requests) == 1
        assert "REDIRECT_REJECTED" in result["data"]["coverage"]["gaps"]


    @pytest.mark.parametrize("status", [403, 429])
    def test_rate_limit_is_explicit_and_does_not_echo_provider_body(self, status):
        result, requests, _ = _observe(lambda _: httpx.Response(status, text="sensitive-provider-body", headers={"x-ratelimit-remaining": "0"}))
        _assert_partial(result)
        assert "RATE_LIMITED" in result["data"]["coverage"]["gaps"]
        assert "sensitive-provider-body" not in json.dumps(result)
        assert len(requests) == 1


    def test_successful_inventory_is_preserved_when_pr_search_is_rate_limited(self):
        normal = _handler()
        def handle(request):
            return httpx.Response(429) if request.url.path == "/search/issues" else normal(request)
        result, _, _ = _observe(handle)
        _assert_partial(result)
        assert result["data"]["state"] == "INCOMPLETE"
        assert result["data"]["counts"]["repositories_observed"] == 1


    @pytest.mark.parametrize("headers,content", [
        ({"content-length": "10000000"}, b"[]"),
        ({"content-length": "invalid"}, b"[]"),
        ({}, b"[" + b" " * 100 + b"]"),
    ])
    def test_response_size_and_content_length_are_bounded(self, monkeypatch, headers, content):
        monkeypatch.setattr(B, "GITHUB_ESTATE_MAX_RESPONSE_BYTES", 64)
        result, requests, _ = _observe(lambda _: httpx.Response(200, headers=headers, content=content))
        _assert_partial(result)
        assert len(requests) == 1


    def test_invalid_json_is_sanitized(self):
        result, _, _ = _observe(lambda _: httpx.Response(200, content=b"sensitive-not-json"))
        _assert_partial(result)
        assert "INVALID_JSON" in result["data"]["coverage"]["gaps"]
        assert "sensitive-not-json" not in json.dumps(result)


    @pytest.mark.parametrize("field,value", [
        ("owner", {"login": "someone-else"}),
        ("full_name", "someone-else/hatun-mcp"),
        ("private", True),
        ("private", 0),
        ("archived", "false"),
        ("disabled", 0),
        ("fork", "true"),
        ("name", "../secrets"),
    ])
    def test_malformed_repository_evidence_is_rejected(self, field, value):
        repository = _repo()
        repository[field] = value
        result, requests, _ = _observe(_handler(repositories=[repository]))
        _assert_partial(result)
        assert len(requests) == 1


    def test_repository_pagination_uses_fixed_paths_and_keeps_each_page_in_evidence(self):
        def handle(request):
            if request.url.path == "/search/issues":
                return httpx.Response(200, json=_search([]))
            assert request.url.path == "/orgs/szl-holdings/repos"
            page = int(request.url.params["page"])
            if page == 1:
                return httpx.Response(200, json=[_repo("alpha")], headers={"link": '<https://attacker.invalid/anything>; rel="next"'})
            assert page == 2
            return httpx.Response(200, json=[_repo("beta")])
        result, requests, _ = _observe(handle)
        assert result["data"]["state"] == "COMPLETE"
        assert len(requests) == 3
        repo_citations = [row for row in result["data"]["citations"] if row["path"] == "/orgs/szl-holdings/repos"]
        assert {row["params"]["page"] for row in repo_citations} == {"1", "2"}
        assert all(len(row["response_sha256"]) == 64 for row in repo_citations)


    def test_duplicate_repository_across_pages_is_not_complete(self):
        def handle(request):
            headers = {"link": '<https://api.github.com/example>; rel="next"'} if request.url.params["page"] == "1" else {}
            return httpx.Response(200, json=[_repo()], headers=headers)
        result, requests, _ = _observe(handle)
        _assert_partial(result)
        assert len(requests) == 2
        assert "DUPLICATE_REPOSITORY" in result["data"]["coverage"]["gaps"]


    def test_repository_pagination_stops_at_hard_cap(self, monkeypatch):
        monkeypatch.setattr(B, "GITHUB_ESTATE_MAX_REPO_PAGES", 2)
        result, requests, _ = _observe(lambda request: httpx.Response(200, json=[_repo(f"repo-{request.url.params['page']}")], headers={"link": '<https://api.github.com/ignored>; rel="next"'}))
        _assert_partial(result)
        assert len(requests) == 2
        assert "REPOSITORY_PAGINATION_LIMIT" in result["data"]["coverage"]["gaps"]


    def test_repository_item_cap_does_not_return_more_than_the_cap(self, monkeypatch):
        monkeypatch.setattr(B, "GITHUB_ESTATE_MAX_REPOSITORIES", 1)
        result, _, _ = _observe(_handler(repositories=[_repo("one"), _repo("two")]))
        _assert_partial(result)
        assert len(result["data"]["repositories"]) <= 1


    @pytest.mark.parametrize("field,value", [("total_count", True), ("total_count", -1), ("incomplete_results", True)])
    def test_invalid_or_incomplete_search_cannot_claim_complete(self, field, value):
        search = _search()
        search[field] = value
        result, requests, _ = _observe(_handler(search=search))
        _assert_partial(result)
        assert len(requests) == 2


    def test_duplicate_search_prs_never_duplicate_observations(self):
        result, requests, _ = _observe(_handler(search=_search([_item(), _item()])))
        _assert_partial(result)
        assert len(requests) == 4
        assert len(result["data"]["open_pull_requests"]) == 1
        assert "DUPLICATE_PULL_REQUEST" in result["data"]["coverage"]["gaps"]


    @pytest.mark.parametrize("field,value", [
        ("number", True), ("number", 0), ("state", "closed"),
        ("pull_request", None),
        ("repository_url", "https://api.github.com/repos/other/hatun-mcp"),
        ("repository_url", "https://api.github.com/repos/szl-holdings/../secret"),
    ])
    def test_search_item_schema_cannot_redirect_or_misidentify_pr(self, field, value):
        item = _item()
        item[field] = value
        result, requests, _ = _observe(_handler(search=_search([item])))
        _assert_partial(result)
        assert len(requests) == 2


    @pytest.mark.parametrize("field,value", [("number", 8), ("number", True), ("state", "closed"), ("merged", True), ("draft", "false")])
    def test_detail_must_match_the_requested_open_pr(self, field, value):
        detail = _detail()
        detail[field] = value
        result, requests, _ = _observe(_handler(detail=detail))
        _assert_partial(result)
        assert result["data"]["open_pull_requests"] == []
        assert len(requests) == 3


    @pytest.mark.parametrize("ref,field,value", [
        ("head", "sha", "main"), ("head", "sha", "A" * 40),
        ("base", "sha", True), ("base", "repo", _repo("different")),
    ])
    def test_detail_refs_are_validated_before_check_fetch(self, ref, field, value):
        detail = _detail()
        detail[ref][field] = value
        result, requests, _ = _observe(_handler(detail=detail))
        _assert_partial(result)
        assert len(requests) == 3


    @pytest.mark.parametrize("field,value", [("head_sha", "c" * 40), ("id", True), ("id", 0)])
    def test_checks_must_be_identified_and_bound_to_observed_head(self, field, value):
        run = _run()
        run[field] = value
        result, _, _ = _observe(_handler(checks={"total_count": 1, "check_runs": [run]}))
        _assert_partial(result)
        assert result["data"]["open_pull_requests"] == []


    def test_duplicate_check_ids_do_not_form_success_evidence(self):
        result, _, _ = _observe(_handler(checks={"total_count": 2, "check_runs": [_run(), _run()]}))
        _assert_partial(result)


    @pytest.mark.parametrize("total", [True, 2, 101])
    def test_check_count_schema_and_truncation_are_explicit(self, total):
        result, _, _ = _observe(_handler(checks={"total_count": total, "check_runs": [_run()]}))
        _assert_partial(result)


    @pytest.mark.parametrize("runs", [[], [_run(conclusion=None)], [_run(conclusion="future-result")], [_run(status="future-status", conclusion=None)]])
    def test_zero_or_unknown_checks_never_claim_success(self, runs):
        result, _, _ = _observe(_handler(checks={"total_count": len(runs), "check_runs": runs}))
        _assert_partial(result)
        assert result["data"]["open_pull_requests"][0]["checks"]["state"] == "UNKNOWN"


    @pytest.mark.parametrize("status,conclusion,state", [
        ("completed", "failure", "FAILURE"),
        ("completed", "cancelled", "FAILURE"),
        ("completed", "timed_out", "FAILURE"),
        ("in_progress", None, "IN_PROGRESS"),
        ("queued", None, "IN_PROGRESS"),
        ("completed", "skipped", "NEUTRAL"),
        ("completed", "neutral", "NEUTRAL"),
    ])
    def test_observed_non_success_check_states_are_preserved(self, status, conclusion, state):
        result, _, _ = _observe(_handler(checks={"total_count": 1, "check_runs": [_run(status=status, conclusion=conclusion)]}))
        assert result["data"]["state"] == "COMPLETE"
        assert result["data"]["open_pull_requests"][0]["checks"]["state"] == state


    def test_request_cap_prevents_additional_network_calls(self, monkeypatch):
        monkeypatch.setattr(B, "GITHUB_ESTATE_MAX_REQUESTS", 2)
        result, requests, _ = _observe()
        _assert_partial(result)
        assert len(requests) == 2
        assert "REQUEST_LIMIT" in result["data"]["coverage"]["gaps"]


    def test_hard_deadline_cancels_stalled_provider_request(self, monkeypatch):
        cancelled = []
        monkeypatch.setattr(B, "GITHUB_ESTATE_TIMEOUT_S", 0.01)
        async def stalled(_):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        result, requests, _ = _observe(stalled)
        _assert_partial(result)
        assert "OVERALL_TIMEOUT" in result["data"]["coverage"]["gaps"]
        assert len(requests) == 1
        assert cancelled == [True]


    def test_transport_exception_is_sanitized(self):
        def fail(_):
            raise httpx.ConnectError("sensitive-transport-context")
        result, _, _ = _observe(fail)
        _assert_partial(result)
        assert "sensitive-transport-context" not in json.dumps(result)


    def test_canonical_digest_covers_snapshot_and_provider_body_hashes(self, monkeypatch):
        monkeypatch.setattr(B, "_github_observed_at", lambda: "2026-09-07T12:00:00Z")
        result, _, _ = _observe()
        snapshot = copy.deepcopy(result["data"])
        evidence = snapshot.pop("evidence")
        expected = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        assert evidence["digest"] == expected == result["evidence_digest_sha256"]
        assert len({row["response_sha256"] for row in snapshot["citations"]}) == 4
        repository_citation = next(row for row in snapshot["citations"] if row["path"] == "/orgs/szl-holdings/repos")
        repository_body = httpx.Response(200, json=[_repo()]).content
        assert repository_citation["response_sha256"] == hashlib.sha256(repository_body).hexdigest()
        assert repository_citation["response_bytes"] == len(repository_body)
        snapshot["open_pull_requests"][0]["head"]["sha"] = "d" * 40
        assert B._github_canonical_digest(snapshot) != expected
        same, _, _ = _observe()
        assert same["evidence_digest_sha256"] == expected


    def test_backend_observation_does_not_claim_it_signed_the_snapshot(self):
        result, _, _ = _observe(signer_mode="PLACEHOLDER")
        assert result["data"]["state"] == "COMPLETE"
        attestation = result["data"]["cryptographic_attestation"]
        assert attestation["state"] == "NOT_SIGNED_BY_OBSERVER"
        assert attestation["envelope_signer_mode"] == "UNSIGNED"
        assert attestation["admissible_for_mutation"] is False


    def test_forbidden_response_is_distinguished_from_rate_limit(self):
        result, _, _ = _observe(lambda _: httpx.Response(403))
        _assert_partial(result)
        assert "HTTP_403" in result["data"]["coverage"]["gaps"]
        assert "RATE_LIMITED" not in result["data"]["coverage"]["gaps"]


    def test_total_response_bytes_are_bounded_across_multiple_requests(self, monkeypatch):
        first_response_bytes = len(httpx.Response(200, json=[_repo()]).content)
        monkeypatch.setattr(B, "GITHUB_ESTATE_MAX_TOTAL_RESPONSE_BYTES", first_response_bytes + 10)
        result, requests, _ = _observe()
        _assert_partial(result)
        assert len(requests) == 2
        assert result["data"]["counts"]["repositories_observed"] == 1
        assert result["data"]["counts"]["response_body_bytes_accepted"] == first_response_bytes

    def test_exhausted_total_byte_budget_stops_queued_pr_requests(self, monkeypatch):
        items = [_item(number=n) for n in range(1, 9)]
        prefix_bytes = (
            len(httpx.Response(200, json=[_repo()]).content)
            + len(httpx.Response(200, json=_search(items)).content)
        )
        # Regression: this 2053-byte cap formerly still issued all eight PR
        # detail GETs and accumulated 6664 observed body bytes.
        assert prefix_bytes + 5 == 2053
        monkeypatch.setattr(B, "GITHUB_ESTATE_MAX_TOTAL_RESPONSE_BYTES", prefix_bytes + 5)

        def handle(request):
            if request.url.path == "/orgs/szl-holdings/repos":
                return httpx.Response(200, json=[_repo()])
            if request.url.path == "/search/issues":
                return httpx.Response(200, json=_search(items))
            if "/pulls/" in request.url.path:
                return httpx.Response(200, json=_detail(number=int(request.url.path.rsplit("/", 1)[1])))
            raise AssertionError("Unexpected fixture endpoint")

        result, requests, _ = _observe(handle)
        _assert_partial(result)
        assert len(requests) == 3
        assert requests[-1].url.path.endswith("/pulls/1")
        assert result["data"]["counts"]["requests_issued"] == 3
        assert result["data"]["counts"]["response_body_bytes_accepted"] == prefix_bytes
        assert "TOTAL_RESPONSE_BYTES_LIMIT" in result["data"]["coverage"]["gaps"]

    @pytest.mark.parametrize("first_chunk_size", [5, 6])
    def test_total_budget_blocks_next_stream_read_and_queued_gets(self, monkeypatch, first_chunk_size):
        items = [_item(number=n) for n in range(1, 9)]
        prefix_bytes = (
            len(httpx.Response(200, json=[_repo()]).content)
            + len(httpx.Response(200, json=_search(items)).content)
        )
        cap = prefix_bytes + 5
        monkeypatch.setattr(B, "GITHUB_ESTATE_MAX_TOTAL_RESPONSE_BYTES", cap)
        yielded = []
        closed = []

        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yielded.append("first")
                yield b" " * first_chunk_size
                yielded.append("forbidden-second")
                yield b" " * 65_536

            async def aclose(self):
                closed.append(True)

        def handle(request):
            if request.url.path == "/orgs/szl-holdings/repos":
                return httpx.Response(200, json=[_repo()])
            if request.url.path == "/search/issues":
                return httpx.Response(200, json=_search(items))
            if "/pulls/" in request.url.path:
                return httpx.Response(200, stream=Stream())
            raise AssertionError("Unexpected fixture endpoint")

        result, requests, _ = _observe(handle)
        _assert_partial(result)
        assert len(requests) == 3
        assert yielded == ["first"]
        assert closed == [True]
        accepted = result["data"]["counts"]["response_body_bytes_accepted"]
        assert accepted == prefix_bytes + (5 if first_chunk_size == 5 else 0)
        assert accepted <= cap
        assert "response_bytes_observed" not in result["data"]["counts"]
        assert result["data"]["limits"]["response_body_bytes_accepted_total"] == cap
        assert result["data"]["limits"]["response_body_accounting"] == (
            "ACCEPTED_APPLICATION_BYTES_TRANSPORT_PREFETCH_NOT_MEASURED"
        )

    def test_inflight_stream_chunks_are_rejected_after_shared_budget_exhaustion(self, monkeypatch):
        items = [_item(number=n) for n in range(1, 9)]
        prefix_bytes = (
            len(httpx.Response(200, json=[_repo()]).content)
            + len(httpx.Response(200, json=_search(items)).content)
        )
        monkeypatch.setattr(B, "GITHUB_ESTATE_MAX_TOTAL_RESPONSE_BYTES", prefix_bytes + 5)
        started = []
        delivered = []
        closed = []
        all_started = None

        class Stream(httpx.AsyncByteStream):
            def __init__(self, number):
                self.number = number

            async def __aiter__(self):
                nonlocal all_started
                if all_started is None:
                    all_started = asyncio.Event()
                started.append(self.number)
                if len(started) == 4:
                    all_started.set()
                await all_started.wait()
                delivered.append(self.number)
                yield b" " * 6
                raise AssertionError("No second stream read is permitted after exhaustion")

            async def aclose(self):
                closed.append(self.number)

        def handle(request):
            if request.url.path == "/orgs/szl-holdings/repos":
                return httpx.Response(200, json=[_repo()])
            if request.url.path == "/search/issues":
                return httpx.Response(200, json=_search(items))
            if "/pulls/" in request.url.path:
                return httpx.Response(200, stream=Stream(int(request.url.path.rsplit("/", 1)[1])))
            raise AssertionError("Unexpected fixture endpoint")

        result, requests, _ = _observe(handle)
        _assert_partial(result)
        # Four reads had already begun; each can deliver its pending chunk, but
        # no pending chunk is accepted and the other four PRs issue no GET.
        assert len(requests) == 6
        assert sorted(started) == sorted(delivered) == sorted(closed) == [1, 2, 3, 4]
        assert result["data"]["counts"]["requests_issued"] == 6
        assert result["data"]["counts"]["response_body_bytes_accepted"] == prefix_bytes
        assert "TOTAL_RESPONSE_BYTES_LIMIT" in result["data"]["coverage"]["gaps"]


    def test_search_pagination_is_partial_even_when_returned_count_matches(self):
        normal = _handler()
        def handle(request):
            if request.url.path == "/search/issues":
                return httpx.Response(200, json=_search(), headers={"link": '<https://api.github.com/ignored>; rel="next"'})
            return normal(request)
        result, requests, _ = _observe(handle)
        _assert_partial(result)
        assert len(requests) == 2


    def test_checks_pagination_never_implies_all_checks_observed(self):
        normal = _handler()
        def handle(request):
            if request.url.path.endswith("/check-runs"):
                return httpx.Response(200, json={"total_count": 1, "check_runs": [_run()]}, headers={"link": '<https://api.github.com/ignored>; rel="next"'})
            return normal(request)
        result, _, _ = _observe(handle)
        _assert_partial(result)


    def test_pr_moved_since_search_is_not_a_complete_observation(self):
        detail = _detail()
        detail["updated_at"] = "2026-09-07T12:01:00Z"
        result, requests, _ = _observe(_handler(detail=detail))
        _assert_partial(result)
        assert len(requests) == 3
        assert "PULL_REQUEST_SEARCH_STALE" in result["data"]["coverage"]["gaps"]


    @pytest.mark.parametrize("body", [b'{"total_count": NaN}', b'{"total_count": Infinity}'])
    def test_nonfinite_json_values_are_rejected(self, body):
        result, _, _ = _observe(lambda _: httpx.Response(200, content=body))
        _assert_partial(result)
        assert "INVALID_JSON" in result["data"]["coverage"]["gaps"]
