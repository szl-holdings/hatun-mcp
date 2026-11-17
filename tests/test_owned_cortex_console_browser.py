"""Actual Chromium -> local TCP ASGI -> MCP -> validated simulated Cortex.

Opt in with HATUN_RUN_BROWSER_TESTS=1; install Playwright plus its Chromium first,
or set HATUN_BROWSER_CHANNEL=msedge for an installed Chromium-based Edge.
Run: python -m pytest tests/test_owned_cortex_console_browser.py -q

Only the upstream JSON transport is simulated. MCP initialize/notification/call,
operator authentication, governance, adapter validation and browser code are real.
The child receives an allowlisted environment and one ephemeral operator key.
It cannot load signing keys, forward receipts, or connect to non-loopback hosts.
This is a SIMULATED integration witness, never a deployment or model-quality test.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "Explain the public doctrine."
TOOL = "szl_owned_cortex_infer"
pytestmark = pytest.mark.skipif(
    os.environ.get("HATUN_RUN_BROWSER_TESTS") != "1",
    reason="opt-in real browser integration; requires Playwright Chromium",
)


def _source_hashes():
    paths = (
        "hatun_mcp/console_v2.py", "hatun_mcp/owned_cortex.py", "hatun_mcp/server.py",
        "hatun_mcp/server_http.py", "tests/owned_cortex_fixtures.py",
        "tests/test_owned_cortex_console_browser.py",
    )
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}


def _serve_fixture() -> None:
    """Run in a fresh child, before any Hatun import."""
    import httpx
    import uvicorn
    from starlette.responses import JSONResponse

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    from owned_cortex_fixtures import HEADERS, contract, denial, proposal, sha, text_sha
    from hatun_mcp import owned_cortex, server_http

    assert "HATUN_MCP_SIGNING_KEY" not in os.environ
    assert "HATUN_MCP_SIGNING_KEY_PATH" not in os.environ
    assert "SZL_RECEIPT_SINK" not in os.environ
    assert server_http.SIGNER.mode != "ECDSA-P256"
    source_hashes = _source_hashes()

    control_path = os.environ["HATUN_BROWSER_FIXTURE_PATH"]
    binding = os.environ["HATUN_BROWSER_FIXTURE_BINDING"]
    calls: list[dict] = []
    finished: list[str] = []
    releases: dict[str, asyncio.Event] = {}

    def deny_outbound(event, arguments):
        if event == "socket.connect":
            address = arguments[1]
            if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1"}:
                raise RuntimeError("browser fixture forbids non-loopback connections")

    sys.addaudithook(deny_outbound)

    async def fake_read_json(client, method, path, limit, payload=None):
        assert set(client.headers) >= {"accept", "cache-control", "user-agent"}
        assert not any(name in client.headers for name in (
            "authorization", "x-api-key", "cookie", "payment-context",
        ))
        if method == "GET":
            assert path == owned_cortex.CONTRACT_PATH
            return 200, contract(), httpx.Headers(HEADERS)
        assert method == "POST" and path == owned_cortex.INFER_PATH
        assert set(payload) == {"prompt", "max_new_tokens", "k"}
        prompt = payload["prompt"]
        calls.append({"prompt": prompt, "tokens": payload["max_new_tokens"], "k": payload["k"]})
        if prompt.startswith("fixture:delay"):
            event = releases.setdefault(prompt, asyncio.Event())
            try:
                await asyncio.wait_for(event.wait(), timeout=15)
            finally:
                finished.append(prompt)
        if prompt == "fixture:unavailable":
            return 503, denial(), httpx.Headers(HEADERS)
        if prompt == "fixture:denial":
            return 422, denial(), httpx.Headers(HEADERS)
        trace_state = {"fixture:trace-unavailable": "UNAVAILABLE",
                       "fixture:trace-absent": "ABSENT"}.get(prompt, "OBSERVED")
        body = proposal(**payload, trace_state=trace_state)
        # Keep screenshots and returned text unmistakably simulated; no model ran.
        text = body["output"]
        if prompt == "fixture:markup":
            text = '<img src=x onerror="window.__proposalExecuted=true">fixture evidence'
        body["output"] = "SIMULATED FIXTURE — no production inference. " + text
        output_sha = body["output_sha256"] = text_sha(body["output"])
        body["claims"][0]["statement_sha256"] = output_sha
        body["claims_sha256"] = sha(body["claims"])
        receipt = body["receipt"]
        receipt["payload"]["output_sha256"] = output_sha
        receipt_sha = receipt["receipt_sha256"] = sha(receipt["payload"])
        body["anatomy_observation"]["event"].update(
            output_sha256=output_sha, receipt_sha256=receipt_sha)
        trace = body.get("trace_observation")
        if trace and trace["state"] == "OBSERVED":
            trace["receipt_sha256"] = receipt_sha
            trace["observation_sha256"] = sha({
                key: value for key, value in trace.items() if key != "observation_sha256"})
        if prompt == "fixture:source":
            body["source_revision"] = "f" * 40
        elif prompt == "fixture:digest":
            body["output_sha256"] = "0" * 64
        return 200, body, httpx.Headers(HEADERS)

    owned_cortex._read_json = fake_read_json

    async def fixture_app(scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith(control_path + "/"):
            action = scope["path"].removeprefix(control_path + "/")
            if scope["method"] == "POST" and action == "release":
                for event in releases.values():
                    event.set()
            elif scope["method"] == "POST" and action == "revoke":
                os.environ.pop(binding, None)
            elif scope["method"] == "POST" and action == "restore":
                os.environ[binding] = "read"
            elif scope["method"] != "GET" or action != "stats":
                await JSONResponse({"error": "fixture route"}, status_code=404)(scope, receive, send)
                return
            await JSONResponse({
                "calls": calls, "finished": finished,
                "receipts": server_http.KHIPU.depth(),
                "signer": server_http.SIGNER.mode, "source_sha256": source_hashes,
            })(scope, receive, send)
            return
        await server_http.app(scope, receive, send)

    uvicorn.run(fixture_app, host="127.0.0.1",
                port=int(os.environ["HATUN_BROWSER_FIXTURE_PORT"]),
                log_level="error", access_log=False)


class Gateway:
    def __init__(self, base, control, key):
        self.base, self.control, self.key = base, control, key

    def control_call(self, action="stats", method="GET"):
        import httpx
        with httpx.Client(trust_env=False, timeout=5) as client:
            response = client.request(method, self.base + self.control + "/" + action)
            response.raise_for_status()
            return response.json()

    def wait(self, predicate, *, page, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = self.control_call()
            if predicate(value):
                return value
            # Dispatch Playwright's route callbacks while the MCP exchange runs.
            page.wait_for_timeout(30)
        raise AssertionError("fixture condition did not become true")


@pytest.fixture(scope="module")
def gateway():
    # Never inherit application tokens, operator bindings or signing-key settings.
    allowed = {
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
        "LOCALAPPDATA", "APPDATA", "USERPROFILE", "SYSTEMDRIVE", "PROGRAMFILES",
        "PROGRAMFILES(X86)", "PROGRAMDATA", "ALLUSERSPROFILE", "HOME", "LANG",
    }
    env = {name: value for name, value in os.environ.items() if name.upper() in allowed}
    key = "szl_browser_fixture_" + secrets.token_hex(24)
    salt = "hatun-browser-fixture/v1"
    fingerprint = hashlib.pbkdf2_hmac("sha256", key.encode(), salt.encode(), 210000).hex()[:16]
    binding = "HATUN_MCP_SCOPE_" + fingerprint
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = "http://127.0.0.1:" + str(port)
    control = "/__browser_fixture_" + secrets.token_hex(16)
    env.update({
        "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8",
        "HATUN_MCP_PUBLIC_BASE": base,
        "HATUN_MCP_ALLOWED_HOSTS": "127.0.0.1:" + str(port),
        "HATUN_MCP_ALLOWED_ORIGINS": base,
        "HATUN_MCP_DISABLE_DYNAMIC": "true",
        "HATUN_MCP_ALLOW_ANON": "false",
        "HATUN_MCP_X402_SCHEME": "off",
        "HATUN_MCP_FP_SALT": salt, "HATUN_MCP_FP_ITERATIONS": "210000",
        "HATUN_BROWSER_FIXTURE_PORT": str(port),
        "HATUN_BROWSER_FIXTURE_PATH": control,
        "HATUN_BROWSER_FIXTURE_BINDING": binding,
        binding: "read",
    })
    temporary = tempfile.TemporaryDirectory(prefix="owned-cortex-browser-")
    log = Path(temporary.name) / "fixture.log"
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(Path(__file__)), "--fixture-server"],
            cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
        )
    gateway = Gateway(base, control, key)
    try:
        import httpx
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail("fixture server failed:\n" + log.read_text(encoding="utf-8")[-6000:])
            try:
                observed = gateway.control_call()
                if observed["signer"] != "ECDSA-P256":
                    gateway.source_hashes = observed["source_sha256"]
                    print("BROWSER_SOURCE_SHA256 " + json.dumps(gateway.source_hashes, sort_keys=True))
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:
            pytest.fail("fixture server startup timed out")
        yield gateway
        assert gateway.source_hashes == _source_hashes(), "source changed during browser validation"
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        temporary.cleanup()


@pytest.fixture(scope="module")
def chromium():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        options = {"headless": True}
        channel = os.environ.get("HATUN_BROWSER_CHANNEL")
        if channel:
            options["channel"] = channel
        # An opt-in run must fail, not silently skip, if Chromium is unavailable.
        browser = playwright.chromium.launch(**options)
        yield browser
        browser.close()


@pytest.fixture
def console(chromium, gateway):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    requests, failures, external = [], [], []

    def observe(request):
        parsed = urlsplit(request.url)
        headers = request.headers
        row = {"method": request.method, "path": parsed.path,
               "same_origin": request.url.startswith(gateway.base + "/"),
               "has_credential": "authorization" in headers or "x-api-key" in headers}
        if request.method == "POST" and parsed.path == "/mcp/":
            row["message"] = request.post_data_json
            row["credential_matches"] = headers.get("authorization") == "Bearer " + gateway.key
            row["no_cookies"] = "cookie" not in headers
        requests.append(row)

    def local_only(route):
        if route.request.url.startswith(gateway.base + "/"):
            route.continue_()
        else:
            external.append(urlsplit(route.request.url).netloc)
            route.abort()

    context.route("**/*", local_only)
    page.on("request", observe)
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(gateway.base, wait_until="networkidle")
    page.locator("#proposal-submit").wait_for(state="visible")
    yield page, requests, gateway
    assert failures == [], "browser JavaScript error: " + repr(failures)
    assert external == [], "unexpected non-loopback browser request"
    assert all(not row["has_credential"] or
               (row["same_origin"] and row["path"] == "/mcp/") for row in requests)
    context.close()


def _submit(console, question=QUESTION, key=None):
    page, _, gateway = console
    page.locator("#proposal-prompt").fill(question)
    page.locator("#proposal-key").fill(gateway.key if key is None else key)
    page.locator("#proposal-submit").click()


def _done(page):
    from playwright.sync_api import expect
    expect(page.locator("#proposal-form")).to_have_attribute("aria-busy", "false", timeout=10000)


def _rows(page):
    return page.locator("#proposal-evidence").evaluate("""node => {
        const labels = Array.from(node.querySelectorAll('dt'));
        const values = Array.from(node.querySelectorAll('dd'));
        return Object.fromEntries(labels.map((label, i) => [label.textContent, values[i].textContent]));
    }""")


def _empty(page):
    assert page.locator("#proposal-output").inner_text() == "No proposal to display."
    assert page.locator("#proposal-evidence").is_hidden()
    assert page.locator("#proposal-evidence").text_content() == ""
    assert page.locator("#proposal-details").is_hidden()
    assert page.locator("#proposal-raw").text_content() == ""


def _success(console, question=QUESTION):
    page, _, _ = console
    _submit(console, question)
    _done(page)
    assert page.locator("#proposal-status").inner_text().startswith("PROPOSAL —")


def test_real_mcp_sequence_is_explicit_and_evidence_is_bound(console):
    page, requests, gateway = console
    assert not [row for row in requests if row["method"] == "POST"]
    before = gateway.control_call()
    assert before["signer"] != "ECDSA-P256"
    _success(console)
    posts = [row for row in requests if row["method"] == "POST"]
    assert [row["message"]["method"] for row in posts] == [
        "initialize", "notifications/initialized", "tools/call"]
    assert all(row["path"] == "/mcp/" and row["credential_matches"] and row["no_cookies"]
               for row in posts)
    assert posts[-1]["message"]["params"] == {
        "name": TOOL, "arguments": {"prompt": QUESTION, "max_new_tokens": 64, "k": 3}}
    assert gateway.control_call()["calls"][-1] == {"prompt": QUESTION, "tokens": 64, "k": 3}
    rows = _rows(page)
    assert rows["Source"] == "a" * 40
    assert rows["Authority"] == "NO_ACTION_AUTHORITY · executed false"
    assert rows["Cortex signature"] == "UNSIGNED_RUNTIME · ephemeral process memory"
    assert rows["Hatun signature"] == "UNSIGNED / PLACEHOLDER"
    assert "OBSERVED" in rows["Trace observation"]
    assert "not independently witnessed" in rows["Trace observation"]
    output = page.locator("#proposal-output").inner_text()
    assert rows["Output SHA-256"] == hashlib.sha256(output.encode()).hexdigest()
    assert "8 locked source formulas" in rows["Doctrine"]
    assert "signatures not verified" in rows["Validation"]
    page.locator("#proposal-details summary").click()
    raw = json.loads(page.locator("#proposal-raw").inner_text())
    assert raw["data"]["upstream"]["evidence_handles"][0]["node_id"] == "doctrine:F1"
    assert raw["data"]["verification"]["latest_deployment_verified"] is False
    assert raw["governance"]["signer_mode"] != "ECDSA-P256"
    assert page.locator("#proposal-key").input_value() == ""
    storage = page.evaluate("""() => ({
        local: {...localStorage}, session: {...sessionStorage}, cookie: document.cookie
    })""")
    assert storage == {"local": {}, "session": {}, "cookie": ""}
    assert gateway.key not in page.content()


@pytest.mark.parametrize("padding", [" \n", "\u0085", "\u001c", "\u001f", "\ufeff"])
def test_padded_question_is_bound_to_the_normalized_request(console, padding):
    page, _, gateway = console
    question = padding + QUESTION + padding
    expected = question.strip()
    _success(console, question)
    assert gateway.control_call()["calls"][-1]["prompt"] == expected
    raw = json.loads(page.locator("#proposal-raw").text_content())
    assert raw["data"]["upstream"]["receipt"]["payload"]["prompt_sha256"] == hashlib.sha256(
        expected.encode()).hexdigest()


@pytest.mark.parametrize(("question", "code"), [
    ("fixture:source", "SOURCE_REVISION_MISMATCH"),
    ("fixture:digest", "OUTPUT_DIGEST_MISMATCH"),
    ("fixture:unavailable", "UPSTREAM_UNAVAILABLE"),
    ("fixture:denial", "UPSTREAM_DECLINED"),
])
def test_bad_upstream_clears_previous_output_and_evidence(console, question, code):
    page, _, gateway = console
    _success(console)
    with page.expect_response(
        lambda response: response.url == gateway.base + "/mcp/"
        and response.request.method == "POST"
        and response.request.post_data_json.get("method") == "tools/call"
    ) as observed:
        _submit(console, question)
        _done(page)
    if code in {"SOURCE_REVISION_MISMATCH", "OUTPUT_DIGEST_MISMATCH"}:
        result = observed.value.json()["result"]
        reply = result.get("structuredContent")
        if reply is None:
            reply = json.loads(result["content"][0]["text"])
        failed = reply["data"]
        assert failed["state"] == "UNAVAILABLE"
        assert failed["verification"]["freshness"] == "UNAVAILABLE"
        assert failed["source_revision"] == "a" * 40
        assert failed["upstream_http_status"] == 200
        assert code in failed["reason_codes"]
    assert code in page.locator("#proposal-status").inner_text()
    _empty(page)


@pytest.mark.parametrize(("question", "label"), [
    ("fixture:trace-unavailable", "UNAVAILABLE"),
    ("fixture:trace-absent", "NOT RETURNED"),
])
def test_optional_trace_states_are_honest(console, question, label):
    page, _, _ = console
    _success(console, question)
    assert label in _rows(page)["Trace observation"]
    assert _rows(page)["Hatun signature"] == "UNSIGNED / PLACEHOLDER"


def test_rejected_key_cannot_call_backend_or_mint_receipt(console):
    page, requests, gateway = console
    _success(console)
    before = gateway.control_call()
    start = len(requests)
    _submit(console, key="szl_fixture_unbound")
    _done(page)
    assert "not admitted" in page.locator("#proposal-status").inner_text()
    _empty(page)
    after = gateway.control_call()
    assert after["calls"] == before["calls"]
    assert after["receipts"] == before["receipts"]
    assert [row["message"]["method"] for row in requests[start:] if row["method"] == "POST"] == [
        "initialize"]


def test_revoked_binding_is_rechecked_on_the_next_request(console):
    page, _, gateway = console
    _success(console)
    before = gateway.control_call("revoke", "POST")
    try:
        _submit(console)
        _done(page)
        assert "not admitted" in page.locator("#proposal-status").inner_text()
        _empty(page)
        after = gateway.control_call()
        assert after["calls"] == before["calls"]
        assert after["receipts"] == before["receipts"]
    finally:
        gateway.control_call("restore", "POST")


@pytest.mark.parametrize("field", ["proposal-prompt", "proposal-key"])
def test_changing_question_or_credential_clears_stale_evidence(console, field):
    page, requests, _ = console
    _success(console)
    count = len([row for row in requests if row["method"] == "POST"])
    page.locator("#" + field).fill("changed")
    _empty(page)
    assert len([row for row in requests if row["method"] == "POST"]) == count


def test_clear_removes_question_key_and_evidence_without_sending(console):
    page, requests, _ = console
    _success(console)
    count = len(requests)
    page.locator("#proposal-clear").click()
    _empty(page)
    assert page.locator("#proposal-prompt").input_value() == ""
    assert page.locator("#proposal-key").input_value() == ""
    assert len(requests) == count


@pytest.mark.parametrize("button", ["proposal-cancel", "proposal-clear"])
def test_stopped_wait_does_not_restore_late_output_or_retry(console, button):
    page, requests, gateway = console
    question = "fixture:delay:" + button
    _submit(console, question)
    gateway.wait(lambda stats: any(row["prompt"] == question for row in stats["calls"]), page=page)
    assert page.locator("#proposal-prompt").is_disabled()
    assert page.locator("#proposal-key").input_value() == ""
    page.locator("#" + button).click()
    _empty(page)
    assert "may still finish" in page.locator("#proposal-status").inner_text()
    gateway.control_call("release", "POST")
    gateway.wait(lambda stats: question in stats["finished"], page=page)
    page.wait_for_timeout(150)
    _empty(page)
    assert len([row for row in requests if row["method"] == "POST"]) == 3
    assert page.locator("#proposal-submit").is_enabled()


def test_model_markup_is_inert_text(console):
    page, _, _ = console
    _success(console, "fixture:markup")
    assert "<img" in page.locator("#proposal-output").inner_text()
    assert page.locator("#proposal-output img").count() == 0
    assert not page.evaluate("Boolean(window.__proposalExecuted)")
    assert _rows(page)["Output SHA-256"] == hashlib.sha256(
        page.locator("#proposal-output").inner_text().encode()).hexdigest()


@pytest.mark.parametrize("width", [360, 390])
def test_narrow_layout_keeps_controls_and_evidence_within_viewport(console, width):
    page, _, _ = console
    page.set_viewport_size({"width": width, "height": 844})
    _success(console)
    page.locator("#proposal-details summary").click()
    metrics = page.evaluate("""() => ({
        width: innerWidth, scroll: document.documentElement.scrollWidth,
        controls: ['proposal-submit','proposal-cancel','proposal-clear','proposal-key']
          .map(id => { const r=document.getElementById(id).getBoundingClientRect();
                       return {left:r.left, right:r.right, height:r.height}; })
    })""")
    assert metrics["scroll"] <= metrics["width"] + 1
    assert all(row["left"] >= 0 and row["right"] <= width + 1 and row["height"] >= 44
               for row in metrics["controls"])



def test_mobile_anchor_and_focused_inputs_are_not_under_the_sticky_rail(console):
    page, _, _ = console
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator('nav.family-links a[href="#proposal"]').click()
    # Wait for the actual smooth anchor scroll rather than disabling motion.
    page.wait_for_timeout(700)
    rail = page.locator(".family-rail").bounding_box()
    heading = page.locator("#proposal h2").bounding_box()
    assert heading["y"] >= rail["y"] + rail["height"] - 1
    for selector in ["#proposal-prompt", "#proposal-key"]:
        page.locator(selector).focus()
        page.wait_for_timeout(150)
        box = page.locator(selector).bounding_box()
        rail = page.locator(".family-rail").bounding_box()
        assert box["y"] >= rail["y"] + rail["height"] - 1
        assert box["y"] + min(box["height"], 44) <= 844
        assert page.locator(selector).evaluate("""node => {
            const r = node.getBoundingClientRect();
            return document.elementFromPoint(r.left + r.width / 2, r.top + 20) === node;
        }""")

def test_operator_key_does_not_grant_raw_signing_or_action_authority(console):
    page, _, gateway = console
    before = gateway.control_call()
    response = page.evaluate("""async ({key}) => {
        const response = await fetch('/mcp/', {
          method:'POST', credentials:'omit',
          headers:{'Content-Type':'application/json',
                   'Accept':'application/json, text/event-stream',
                   'Authorization':'Bearer '+key,
                   'X-Sovereign-Mode':'true', 'X-Second-Approver':'fixture-other'},
          body:JSON.stringify({jsonrpc:'2.0',id:'denied',method:'tools/call',
                               params:{name:'dsse_sign',arguments:{payload:{}}}})
        });
        return {status:response.status};
    }""", {"key": gateway.key})
    assert response["status"] == 403
    after = gateway.control_call()
    assert after["calls"] == before["calls"]
    assert after["receipts"] == before["receipts"]
    _empty(page)


if __name__ == "__main__" and sys.argv[1:] == ["--fixture-server"]:
    _serve_fixture()
