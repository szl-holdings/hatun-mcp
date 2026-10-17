"""Authorized public-data path through the pinned Second Brain app.

The remote Space hostname is not this test. Set SZL_SECOND_BRAIN_APP to the
checkout that contains app_operational.py. The adapter uses its real HTTP
transport against that process.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from hatun_mcp.adapters.second_brain import ControllerGrant, SecondBrainAdapter

APP = os.environ.get("SZL_SECOND_BRAIN_APP", "")
pytestmark = pytest.mark.skipif(not APP, reason="SZL_SECOND_BRAIN_APP is not set")

NOW = 1_700_000_000
PIN = "3a7d935f159abc1b13915dddb6de72ac8eb395a2"


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait(url: str) -> None:
    deadline = time.time() + 30
    last = "not-started"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
                last = str(response.status)
        except Exception as exc:
            last = type(exc).__name__
        time.sleep(0.25)
    raise AssertionError(last)


def test_authorized_public_handles_round_trip():
    port = _port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app_operational:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=APP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait(base + "/api/v1/retrieval-capabilities")
        grant = ControllerGrant(
            principal="controller.public",
            tenant="public",
            scope="public_handles",
            purpose="public_retrieval",
            policy_revision=PIN,
            not_before=NOW - 10,
            expires_at=NOW + 60,
        )
        adapter = SecondBrainAdapter(base_url=base, grant=grant, clock=lambda: NOW)
        catalog = asyncio.run(adapter.fetch_catalog())
        assert catalog.reachable is True
        assert catalog.http_status == 200
        assert catalog.tools
        result = asyncio.run(adapter.call("retrieve_handles", {"query": "governed receipts", "k": 3}))
        assert result["deployed"] is True
        assert result["http_status"] == 200
        assert result["error"] is None
        data = result["data"]
        assert data["hydrated"] is False
        assert data["content_access"] == "HANDLES_ONLY"
        assert "documents" not in data
        assert data["state"] in {"AVAILABLE", "ABSTAIN"}
        assert isinstance(data["evidence"], list)
        for row in data["evidence"]:
            assert len(row["sha256"]) == 64
        if data["state"] == "AVAILABLE":
            assert data["handles"]
            assert data["evidence"]
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
