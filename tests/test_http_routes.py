"""HTTP-route tests for the landing-page CTA targets.

These lock the three landing-page buttons to real, resolving targets so a
regression (a renamed route, a dropped alias, a /mcp -> http:// downgrade)
fails CI instead of shipping a dead button to the Space:

  * "Inspect the server card" -> the canonical card and every short alias
    return 200 with the real server-card JSON (not a 404 / not a stub).
  * "Source on GitHub" -> the console links the real public repo.
  * "Connect an agent" -> the connect descriptor and the in-page config
    snippet point at the trailing-slash /mcp/ endpoint, not the bare /mcp
    that 307-redirects (and downgrades to http:// behind the HF proxy).

Run hermetically (no organ network): HATUN_MCP_DISABLE_DYNAMIC=true.
SPDX-License-Identifier: Apache-2.0
"""
import os

os.environ.setdefault("HATUN_MCP_DISABLE_DYNAMIC", "true")
os.environ.setdefault("HATUN_MCP_BACKEND_TIMEOUT", "1.0")

from starlette.testclient import TestClient  # noqa: E402

from hatun_mcp.server_http import app  # noqa: E402
from hatun_mcp.console import CONSOLE_HTML  # noqa: E402

BASE = "https://szlholdings-hatun-mcp.hf.space"
REPO = "https://github.com/szl-holdings/hatun-mcp"

client = TestClient(app, base_url=BASE)

# Every path a human or registry might poke for "the server card".
CARD_PATHS = [
    "/.well-known/mcp/server-card.json",
    "/.well-known/mcp",
    "/.well-known/mcp/",
    "/server-card",
    "/card",
]


def test_server_card_and_aliases_serve_real_card():
    for path in CARD_PATHS:
        r = client.get(path, headers={"accept": "application/json"},
                       follow_redirects=False)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        body = r.json()
        # Real card: actual server metadata + the server's actual tools.
        assert body["serverInfo"]["name"] == "hatun-mcp"
        assert len(body["tools"]) >= 1
        assert "governance" in body


def test_no_card_path_404s():
    for path in CARD_PATHS:
        r = client.get(path, headers={"accept": "application/json"},
                       follow_redirects=False)
        assert r.status_code != 404, f"{path} regressed to 404"


def test_connect_descriptor_points_at_trailing_slash_mcp():
    r = client.get("/connect", headers={"accept": "application/json"})
    assert r.status_code == 200
    info = r.json()
    # Must be the trailing-slash endpoint (the bare /mcp 307-redirects and the
    # Location downgrades to http:// behind the HF reverse proxy).
    assert info["mcp_endpoint"] == f"{BASE}/mcp/"
    assert info["mcp_endpoint"].endswith("/mcp/")
    assert info["docs"] == REPO


def test_index_json_advertises_trailing_slash_mcp():
    r = client.get("/", headers={"accept": "application/json"})
    assert r.status_code == 200
    j = r.json()
    assert j["mcp_endpoint"] == "/mcp/"
    assert j["connect"] == "/connect"
    assert j["docs"] == REPO


def test_healthz_and_pubkey_resolve():
    assert client.get("/healthz").status_code == 200
    assert client.get("/pubkey").status_code == 200


def test_console_source_button_links_real_repo():
    # "Source on GitHub" button + footer must link the real public repo.
    assert f'href="{REPO}"' in CONSOLE_HTML


def test_console_connect_snippet_uses_trailing_slash_mcp():
    # The in-page connect config must not steer clients at the bare /mcp.
    assert f"{BASE}/mcp/" in CONSOLE_HTML
    assert f'{BASE}/mcp"' not in CONSOLE_HTML
    assert f"{BASE}/mcp<" not in CONSOLE_HTML
