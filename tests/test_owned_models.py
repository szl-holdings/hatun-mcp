"""Tests for the opt-in SZL-owned model gateway.

No test contacts a real provider. Transport is mocked and secrets are cleared
between tests so the default llm_tiers behavior remains deterministic.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hatun_mcp.adapters.llm import LlmAdapter  # noqa: E402


_ENV_KEYS = (
    "SZL_OWNED_MODELS_ENABLED",
    "SZL_MODEL_ENDPOINTS_JSON",
    "SZL_MODEL_ALLOWED_HOSTS",
    "SZL_MODEL_ALLOW_LOCAL",
    "SZL_MODEL_GATEWAY_TOKEN",
    "SZL_HF_ROUTER_URL",
    "SZL_HF_PROVIDER_SUFFIX",
    "HF_TOKEN",
)


@pytest.fixture(autouse=True)
def _clean_model_environment(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class CaptureTransport(httpx.AsyncBaseTransport):
    def __init__(self, *, status: int = 200, payload=None, redirect: str | None = None):
        self.status = status
        self.payload = payload if payload is not None else {
            "id": "chatcmpl-test",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        }
        self.redirect = redirect
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        headers = {"content-type": "application/json"}
        if self.redirect is not None:
            headers["location"] = self.redirect
        return httpx.Response(
            self.status,
            headers=headers,
            content=json.dumps(self.payload).encode("utf-8"),
        )


def _install_transport(monkeypatch, transport: CaptureTransport) -> None:
    original = httpx.AsyncClient.__init__

    def patched(self, *args, **kwargs):
        kwargs["transport"] = transport
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)


def _tool_names(adapter: LlmAdapter) -> list[str]:
    catalog = asyncio.run(adapter.fetch_catalog())
    return [tool.mcp_name for tool in catalog.tools]


def test_owned_model_tools_are_opt_in():
    assert _tool_names(LlmAdapter()) == ["llm_tiers"]


def test_registry_is_visible_without_inference_credentials(monkeypatch):
    monkeypatch.setenv("SZL_OWNED_MODELS_ENABLED", "1")
    assert _tool_names(LlmAdapter()) == ["llm_tiers", "llm_models"]

    result = asyncio.run(LlmAdapter().call("models", {}))
    assert result["error"] is None
    models = result["data"]["models"]
    by_id = {model["id"]: model for model in models}
    assert by_id["SZLHOLDINGS/SZL-Khipu-1.5B"]["callable"] is True
    assert by_id["SZLHOLDINGS/MiniEmbed-Nano"]["callable"] is False
    assert not any(model["runtime_configured"] for model in models)


def test_registry_never_returns_secrets(monkeypatch):
    monkeypatch.setenv("SZL_OWNED_MODELS_ENABLED", "1")
    monkeypatch.setenv("HF_TOKEN", "hf_do_not_leak")
    result = asyncio.run(LlmAdapter().call("models", {}))
    encoded = json.dumps(result, sort_keys=True)
    assert "hf_do_not_leak" not in encoded


def test_chat_registers_when_hf_router_is_configured(monkeypatch):
    monkeypatch.setenv("SZL_OWNED_MODELS_ENABLED", "1")
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    assert _tool_names(LlmAdapter()) == [
        "llm_tiers",
        "llm_models",
        "llm_chat",
    ]


def test_grounded_chat_routes_to_khipu_through_hf_router(monkeypatch):
    monkeypatch.setenv("SZL_OWNED_MODELS_ENABLED", "1")
    monkeypatch.setenv("HF_TOKEN", "hf_test_secret")
    transport = CaptureTransport()
    _install_transport(monkeypatch, transport)

    result = asyncio.run(
        LlmAdapter().call(
            "chat",
            {"prompt": "Summarize the evidence.", "task": "grounded", "max_tokens": 64},
        )
    )

    assert result["error"] is None
    assert result["data"]["selected_model"] == "SZLHOLDINGS/SZL-Khipu-1.5B"
    assert result["data"]["authority"] == "advisory_grounded_only"
    assert result["endpoint"] == "https://router.huggingface.co/v1/chat/completions"
    request = transport.requests[-1]
    assert str(request.url) == "https://router.huggingface.co/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer hf_test_secret"
    body = json.loads(request.content)
    assert body["model"] == "SZLHOLDINGS/SZL-Khipu-1.5B"
    assert body["stream"] is False


def test_task_specific_adapter_falls_back_honestly(monkeypatch):
    monkeypatch.setenv("SZL_OWNED_MODELS_ENABLED", "1")
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    transport = CaptureTransport()
    _install_transport(monkeypatch, transport)

    result = asyncio.run(
        LlmAdapter().call(
            "chat",
            {"prompt": "Classify this.", "task": "triage"},
        )
    )

    assert result["error"] is None
    assert result["data"]["selected_model"] == "SZLHOLDINGS/SZL-Khipu-1.5B"
    assert "fallback:grounded_default" in result["data"]["routing_reason"]


def test_explicit_unconfigured_adapter_fails_closed(monkeypatch):
    monkeypatch.setenv("SZL_OWNED_MODELS_ENABLED", "1")
    monkeypatch.setenv("HF_TOKEN", "hf_test")

    result = asyncio.run(
        LlmAdapter().call(
            "chat",
            {
                "prompt": "Classify this.",
                "task": "triage",
                "model": "SZLHOLDINGS/szl-triage-qwen3.5-0.8b-lora-study5",
            },
        )
    )

    assert result["error"] == "model_runtime_not_configured"
    assert "dedicated endpoint required" in result["reason"]


def test_custom_endpoint_uses_gateway_token_not_hf_token(monkeypatch):
    monkeypatch.setenv("SZL_OWNED_MODELS_ENABLED", "1")
    monkeypatch.setenv("HF_TOKEN", "hf_must_not_be_forwarded")
    monkeypatch.setenv("SZL_MODEL_GATEWAY_TOKEN", "gateway_secret")
    monkeypatch.setenv("SZL_MODEL_ALLOWED_HOSTS", "models.example.test")
    monkeypatch.setenv(
        "SZL_MODEL_ENDPOINTS_JSON",
        json.dumps(
            {
                "SZLHOLDINGS/WILLAY": {
                    "url": "https://models.example.test/v1/chat/completions",
                    "model": "willay",
                }
            }
        ),
    )
    transport = CaptureTransport()
    _install_transport(monkeypatch, transport)

    result = asyncio.run(
        LlmAdapter().call(
            "chat",
            {
                "prompt": "State the doctrine boundary.",
                "task": "identity",
                "model": "SZLHOLDINGS/WILLAY",
            },
        )
    )

    assert result["error"] is None
    assert result["endpoint"] == "configured://SZLHOLDINGS/WILLAY"
    request = transport.requests[-1]
    assert request.headers["authorization"] == "Bearer gateway_secret"
    assert "hf_must_not_be_forwarded" not in request.headers["authorization"]
    assert json.loads(request.content)["model"] == "willay"


def test_unknown_or_fixture_model_is_rejected(monkeypatch):
    monkeypatch.setenv("SZL_OWNED_MODELS_ENABLED", "1")

    unknown = asyncio.run(
        LlmAdapter().call(
            "chat",
            {"prompt": "x", "model": "SZLHOLDINGS/not-real"},
        )
    )
    assert unknown["error"] == "invalid_arguments"

    fixture = asyncio.run(
        LlmAdapter().call(
            "chat",
            {"prompt": "x", "model": "SZLHOLDINGS/MiniEmbed-Nano"},
        )
    )
    assert fixture["error"] == "invalid_arguments"
    assert "not a callable generation model" in fixture["reason"]


def test_redirect_is_rejected_before_credentials_can_follow(monkeypatch):
    monkeypatch.setenv("SZL_OWNED_MODELS_ENABLED", "1")
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    transport = CaptureTransport(
        status=307,
        redirect="https://evil.example/steal",
    )
    _install_transport(monkeypatch, transport)

    result = asyncio.run(
        LlmAdapter().call(
            "chat",
            {"prompt": "x", "task": "grounded"},
        )
    )

    assert result["error"] == "redirect_rejected"
    assert len(transport.requests) == 1


def test_endpoint_override_fields_are_not_accepted(monkeypatch):
    monkeypatch.setenv("SZL_OWNED_MODELS_ENABLED", "1")
    result = asyncio.run(
        LlmAdapter().call(
            "chat",
            {
                "prompt": "x",
                "endpoint": "https://evil.example/v1/chat/completions",
            },
        )
    )
    assert result["error"] == "invalid_arguments"
    assert "unsupported arguments" in result["reason"]
