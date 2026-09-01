"""Contract for /api/console-state — the console's real-data backend.

The human console renders NOTHING it did not read from this process. These tests
lock that contract:

  * the tool catalogue served to the console is enumerated from the LIVE FastMCP
    registry and matches ``mcp._tool_manager.list_tools()`` exactly (a hand-written
    list would drift; this fails instead).
  * parity between the published server card and the runtime registry is measured,
    not asserted.
  * unreadable values carry an honest label (UNAVAILABLE) and no number.
  * the console HTML ships no seeded numbers and reads the Python endpoint.

Run hermetically (no organ network): HATUN_MCP_DISABLE_DYNAMIC=true.
SPDX-License-Identifier: Apache-2.0
"""
import os
import re

os.environ.setdefault("HATUN_MCP_DISABLE_DYNAMIC", "true")
os.environ.setdefault("HATUN_MCP_BACKEND_TIMEOUT", "1.0")

from starlette.testclient import TestClient  # noqa: E402

from hatun_mcp import server_http, state  # noqa: E402
from hatun_mcp.console import CONSOLE_HTML  # noqa: E402
from hatun_mcp.server import KHIPU, mcp  # noqa: E402

BASE = "https://szlholdings-hatun-mcp.hf.space"
client = TestClient(server_http.app, base_url=BASE)


def _state() -> dict:
    response = client.get("/api/console-state")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_tool_catalogue_is_the_live_registry_not_a_written_list():
    payload = _state()
    assert payload["tools"]["state"] == "MEASURED"
    served = [tool["name"] for tool in payload["tools"]["items"]]
    live = sorted(tool.name for tool in mcp._tool_manager.list_tools())
    assert served == live
    assert payload["tools"]["count"] == len(live)
    # every entry carries its real input-schema shape
    for tool in payload["tools"]["items"]:
        assert tool["parameters_total"] >= tool["parameters_required"] >= 0
        assert tool["parameters_total"] == len(tool["parameter_names"])


def test_card_parity_is_measured_against_the_published_card():
    payload = _state()
    parity = payload["card_parity"]
    assert parity["state"] in {"MATCH", "DIVERGENT"}
    assert parity["card_tool_count"] == len(state.card_tool_names())
    assert parity["runtime_tool_count"] == payload["tools"]["count"]
    if parity["state"] == "MATCH":
        assert parity["only_in_card"] == [] and parity["only_in_runtime"] == []


def test_khipu_depth_and_head_are_read_from_the_live_chain():
    payload = _state()
    assert payload["khipu"]["receipts_this_process"] == KHIPU.depth()
    assert payload["khipu"]["head_hash"] == KHIPU.head_hash()
    assert payload["khipu"]["chain"] in {"VERIFIED", "FAILED", "UNAVAILABLE"}


def test_unreadable_values_use_honest_labels_never_numbers(monkeypatch):
    # No injected revision -> the build panel must say UNAVAILABLE and carry no value.
    monkeypatch.delenv("SZL_GIT_SHA", raising=False)
    payload = _state()
    assert payload["build"]["state"] == "UNAVAILABLE"
    assert payload["build"]["revision"] is None
    # PLACEHOLDER signer must never be reported as SIGNED.
    signing = payload["signing"]
    assert signing["state"] in {"SIGNED", "UNSIGNED"}
    if signing["signer_mode"] != "ECDSA-P256":
        assert signing["state"] == "UNSIGNED"
        assert signing["algorithm"] is None
    assert signing["transparency_log"] == "UNAVAILABLE"


def test_unreadable_tool_registry_degrades_without_inventing_a_count():
    class Broken:
        @property
        def _tool_manager(self):
            raise RuntimeError("registry unavailable")

        @property
        def _resource_manager(self):
            raise RuntimeError("registry unavailable")

    payload = state.console_state(
        mcp=Broken(),
        khipu=KHIPU,
        signer=server_http.SIGNER,
        doctrine=server_http.DOCTRINE,
    )
    assert payload["tools"]["state"] == "UNAVAILABLE"
    assert payload["tools"]["count"] is None
    assert payload["tools"]["items"] == []
    assert payload["card_parity"]["state"] == "UNAVAILABLE"
    assert payload["card_parity"]["runtime_tool_count"] is None


def test_index_descriptor_advertises_the_console_state_route():
    body = client.get("/", headers={"accept": "application/json"}).json()
    assert body["console_state"] == "/api/console-state"


def test_console_reads_the_python_endpoint_and_ships_no_seeded_numbers():
    assert "/api/console-state" in CONSOLE_HTML
    # the console must not carry a baked-in metrics snapshot any more
    assert "SNAPSHOT" not in CONSOLE_HTML
    assert "__SNAPSHOT_JSON__" not in CONSOLE_HTML
    # honest labels must be present for the degraded path
    assert "UNAVAILABLE" in CONSOLE_HTML
    # doctrine v11: Lambda is never a theorem on a governed surface
    assert "Conjecture&nbsp;1 · not a theorem" in CONSOLE_HTML


def test_console_is_monochrome_and_makes_no_offchain_fetch():
    # design system: no color pop anywhere in the stylesheet/markup.
    hex_colors = set(
        match.lower() for match in re.findall(r"#[0-9a-fA-F]{6}\b", CONSOLE_HTML)
    )
    allowed = {
        "#000000", "#0a0a0b", "#0d0d0f", "#ffffff", "#f0eee6",
        "#e8e8ea", "#9a9a9e", "#5f5f63", "#1c1c1f", "#2a2a2e",
    }
    assert hex_colors <= allowed, sorted(hex_colors - allowed)
    # every rgb()/rgba() literal must be neutral (r == g == b) or the cream token.
    for r, g, b in re.findall(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", CONSOLE_HTML):
        triple = (int(r), int(g), int(b))
        assert triple[0] == triple[1] == triple[2] or triple == (240, 238, 230), triple
    # sovereign: no CDN, no webfont fetch, no cross-origin data pull.
    # (the only http:// literal permitted is the inline SVG namespace, never fetched)
    assert "http://" not in CONSOLE_HTML.replace("http://www.w3.org/2000/svg", "")
    for host in ("fonts.googleapis.com", "cdn.jsdelivr.net", "unpkg.com",
                 "https://a-11-oy.com"):
        assert host not in CONSOLE_HTML


def test_console_uses_one_shared_card_component():
    # a single card factory + a single .card rule — not per-section variants.
    assert CONSOLE_HTML.count("function card(o){") == 1
    assert re.search(r"\n\.card\{", CONSOLE_HTML) is not None
    # grade/state is rendered as text in a neutral chip, never a colored pill
    assert "border:1px solid currentColor" in CONSOLE_HTML


def test_console_is_mobile_first():
    # single column by default; multi-column only at >=1000px
    assert "grid-template-columns:1fr" in CONSOLE_HTML
    assert "@media (min-width:1000px)" in CONSOLE_HTML
    assert "viewport-fit=cover" in CONSOLE_HTML
    assert "env(safe-area-inset-left)" in CONSOLE_HTML
    assert "prefers-reduced-motion" in CONSOLE_HTML


def test_csp_connect_src_matches_what_the_console_actually_fetches():
    csp = client.get("/", headers={"accept": "text/html"}).headers[
        "content-security-policy"
    ]
    assert "connect-src 'self';" in csp
