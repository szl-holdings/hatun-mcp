#!/usr/bin/env python3
"""Apply the bounded Hatun-MCP Space source-binding changes."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SERVER = ROOT / "hatun_mcp/server_http.py"
HTTP_TESTS = ROOT / "tests/test_http_routes.py"

FRONTMATTER = """---
title: Hatun MCP — Governed Agent Gateway
emoji: 🪢
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Source-bound MCP gateway with PURIQ gates, Khipu receipts, and DSSE responses
---

"""

BUILD_INFO_FUNCTION = '''async def build_info(request: Request):
    """Expose the exact protected Git revision injected by the Space deployer."""
    revision = os.environ.get("SZL_GIT_SHA", "").strip().lower()
    observed = len(revision) == 40 and all(
        character in "0123456789abcdef" for character in revision
    )
    return JSONResponse(
        {
            "service": "hatun-mcp",
            "build": {
                "state": "OBSERVED" if observed else "UNAVAILABLE",
                "revision": revision if observed else None,
            },
            "runtime": {
                "transport": "streamable-http",
                "protocol_revision": DOCTRINE["protocol_revision"],
            },
            "receipt_minted": False,
        },
        status_code=200 if observed else 503,
        headers={"Cache-Control": "no-store"},
    )


'''

BUILD_INFO_TESTS = '''def test_build_info_is_exact_source_bound(monkeypatch):
    revision = "a" * 40
    monkeypatch.setenv("SZL_GIT_SHA", revision)
    response = client.get("/api/build-info")
    body = response.json()
    assert response.status_code == 200
    assert body["build"] == {"state": "OBSERVED", "revision": revision}
    assert body["runtime"]["transport"] == "streamable-http"
    assert body["receipt_minted"] is False
    assert response.headers["cache-control"] == "no-store"


def test_build_info_fails_closed_without_exact_revision(monkeypatch):
    monkeypatch.setenv("SZL_GIT_SHA", "not-a-full-sha")
    response = client.get("/api/build-info")
    body = response.json()
    assert response.status_code == 503
    assert body["build"] == {"state": "UNAVAILABLE", "revision": None}
    assert body["receipt_minted"] is False


'''


def patch_readme() -> bool:
    text = README.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        return False
    README.write_text(FRONTMATTER + text, encoding="utf-8")
    return True


def patch_server() -> bool:
    text = SERVER.read_text(encoding="utf-8")
    changed = False
    if "async def build_info(request: Request):" not in text:
        marker = "async def healthz(request: Request):\n"
        if marker not in text:
            raise RuntimeError("healthz insertion point not found")
        text = text.replace(marker, BUILD_INFO_FUNCTION + marker, 1)
        changed = True

    index_old = '"healthz": "/healthz", "readyz": "/readyz", "pubkey": "/pubkey",'
    index_new = (
        '"healthz": "/healthz", "readyz": "/readyz", '
        '"build_info": "/api/build-info", "pubkey": "/pubkey",'
    )
    if index_new not in text:
        if index_old not in text:
            raise RuntimeError("index descriptor marker not found")
        text = text.replace(index_old, index_new, 1)
        changed = True

    route = '        Route("/api/build-info", build_info),\n'
    if route not in text:
        marker = '        Route("/healthz", healthz),\n'
        if marker not in text:
            raise RuntimeError("health route marker not found")
        text = text.replace(marker, marker + route, 1)
        changed = True

    if changed:
        SERVER.write_text(text, encoding="utf-8")
    return changed


def patch_http_tests() -> bool:
    text = HTTP_TESTS.read_text(encoding="utf-8")
    if "def test_build_info_is_exact_source_bound" in text:
        return False
    marker = "def test_readyz_separates_liveness_from_signed_release_readiness():\n"
    if marker not in text:
        raise RuntimeError("HTTP test insertion point not found")
    text = text.replace(marker, BUILD_INFO_TESTS + marker, 1)
    HTTP_TESTS.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    changed = patch_readme() | patch_server() | patch_http_tests()
    print("changed=true" if changed else "changed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
