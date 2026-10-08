"""
hatun_mcp.adapters.llm — a11oy LLM tier router plus an opt-in SZL-owned model gateway.

The existing `llm_tiers` tool remains the default surface.  Owned-model tools are
registered only when SZL_OWNED_MODELS_ENABLED=1:

* llm_models — local, source-bound registry and runtime-configuration status.
* llm_chat   — governed OpenAI-compatible chat call to an allowlisted SZL model.

The runtime supports Hugging Face Inference Providers for explicitly eligible
full models and dedicated/self-hosted OpenAI-compatible endpoints supplied via
SZL_MODEL_ENDPOINTS_JSON.  Credentials are read from environment variables and
are never returned.  Redirects are rejected so bearer tokens cannot be forwarded
to an unapproved origin.

A successful model-card lookup, endpoint-compatible tag, or HTTP response is not
treated as quality, deployment parity, or action authority.  Every invocation is
still wrapped by Hatun's Yuyay gate, Khipu receipt, and DSSE envelope.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from .. import backends as B
from .base import CatalogResult, OrganAdapter, OrganTool, DEFAULT_TIMEOUT, GOVERNANCE_CRITICAL


_HF_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
_MAX_RESPONSE_BYTES = 2_000_000
_MAX_MESSAGE_COUNT = 32
_MAX_MESSAGE_CHARS = 65_536
_MAX_SINGLE_MESSAGE_CHARS = 32_768
_TOKEN_ENV_RE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_TRUTHY = {"1", "true", "yes", "on"}

# Source observations were refreshed from the public Hub metadata on 2026-10-08.
# These records are routing metadata only.  They do not establish benchmark
# quality, endpoint availability, or permission for autonomous action.
_OWNED_MODELS: dict[str, dict[str, Any]] = {
    "SZLHOLDINGS/SZL-Khipu-1.5B": {
        "label": "Khipu 1.5B",
        "artifact_kind": "full_model",
        "base_model": "Qwen/Qwen2.5-1.5B-Instruct",
        "tasks": ["general", "grounded", "retrieval", "synthesis"],
        "authority": "advisory_grounded_only",
        "serving": "hf_router_or_dedicated_endpoint",
        "router_eligible": True,
        "callable": True,
        "default": True,
    },
    "SZLHOLDINGS/chaski": {
        "label": "Chaski",
        "artifact_kind": "full_model",
        "base_model": "Qwen/Qwen3.5-0.8B",
        "tasks": ["proposal", "research", "multimodal_text"],
        "authority": "proposal_only",
        "serving": "hf_router_or_dedicated_endpoint",
        "router_eligible": True,
        "callable": True,
        "default": False,
    },
    "SZLHOLDINGS/WILLAY": {
        "label": "WILLAY",
        "artifact_kind": "peft_adapter",
        "base_model": "Qwen/Qwen2.5-0.5B-Instruct",
        "tasks": ["identity", "doctrine"],
        "authority": "advisory",
        "serving": "dedicated_endpoint_required",
        "router_eligible": False,
        "callable": True,
        "default": False,
    },
    "SZLHOLDINGS/brain-navigator-r2": {
        "label": "Brain Navigator R2",
        "artifact_kind": "peft_adapter",
        "base_model": "Qwen/Qwen3.5-0.8B",
        "tasks": ["navigation", "research_navigation"],
        "authority": "proposal_only",
        "serving": "dedicated_endpoint_required",
        "router_eligible": False,
        "callable": True,
        "default": False,
    },
    "SZLHOLDINGS/szl-triage-qwen3.5-0.8b-lora-study5": {
        "label": "SZL Triage Study 5",
        "artifact_kind": "peft_adapter_study",
        "base_model": "unsloth/Qwen3.5-0.8B",
        "tasks": ["triage", "classification"],
        "authority": "experimental_advisory",
        "serving": "dedicated_endpoint_required",
        "router_eligible": False,
        "callable": True,
        "default": False,
    },
    "SZLHOLDINGS/A11OY-MINI": {
        "label": "A11OY Mini",
        "artifact_kind": "gguf",
        "base_model": None,
        "tasks": ["offline", "local"],
        "authority": "advisory",
        "serving": "llama_cpp_or_dedicated_endpoint",
        "router_eligible": False,
        "callable": True,
        "default": False,
    },
    "SZLHOLDINGS/MiniEmbed-Nano": {
        "label": "MiniEmbed Nano",
        "artifact_kind": "numpy_reference_fixture",
        "base_model": None,
        "tasks": ["fixture", "evaluation"],
        "authority": "test_fixture_only",
        "serving": "not_a_general_neural_embedder",
        "router_eligible": False,
        "callable": False,
        "default": False,
    },
}

_TASK_DEFAULTS = {
    "general": "SZLHOLDINGS/SZL-Khipu-1.5B",
    "grounded": "SZLHOLDINGS/SZL-Khipu-1.5B",
    "retrieval": "SZLHOLDINGS/SZL-Khipu-1.5B",
    "synthesis": "SZLHOLDINGS/SZL-Khipu-1.5B",
    "proposal": "SZLHOLDINGS/chaski",
    "research": "SZLHOLDINGS/chaski",
    "multimodal_text": "SZLHOLDINGS/chaski",
    "identity": "SZLHOLDINGS/WILLAY",
    "doctrine": "SZLHOLDINGS/WILLAY",
    "navigation": "SZLHOLDINGS/brain-navigator-r2",
    "research_navigation": "SZLHOLDINGS/brain-navigator-r2",
    "triage": "SZLHOLDINGS/szl-triage-qwen3.5-0.8b-lora-study5",
    "classification": "SZLHOLDINGS/szl-triage-qwen3.5-0.8b-lora-study5",
    "offline": "SZLHOLDINGS/A11OY-MINI",
    "local": "SZLHOLDINGS/A11OY-MINI",
}


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _owned_models_enabled() -> bool:
    return _flag("SZL_OWNED_MODELS_ENABLED")


def _endpoint_map() -> tuple[dict[str, dict[str, str]], str | None]:
    raw = os.environ.get("SZL_MODEL_ENDPOINTS_JSON", "").strip()
    if not raw:
        return {}, None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}, "SZL_MODEL_ENDPOINTS_JSON is not valid JSON"
    if not isinstance(parsed, dict):
        return {}, "SZL_MODEL_ENDPOINTS_JSON must be a JSON object"

    normalized: dict[str, dict[str, str]] = {}
    for model_id, value in parsed.items():
        if model_id not in _OWNED_MODELS:
            return {}, f"endpoint map contains unknown model: {model_id}"
        if isinstance(value, str):
            spec: dict[str, Any] = {"url": value}
        elif isinstance(value, dict):
            spec = value
        else:
            return {}, f"endpoint map entry for {model_id} must be a URL string or object"

        url = spec.get("url")
        if not isinstance(url, str) or not url.strip():
            return {}, f"endpoint map entry for {model_id} has no URL"
        provider_model = spec.get("model", model_id)
        token_env = spec.get("token_env", "")
        if not isinstance(provider_model, str) or not provider_model.strip():
            return {}, f"endpoint map entry for {model_id} has an invalid provider model"
        if token_env is None:
            token_env = ""
        if not isinstance(token_env, str) or (
            token_env and not _TOKEN_ENV_RE.fullmatch(token_env)
        ):
            return {}, f"endpoint map entry for {model_id} has an invalid token_env"
        normalized[model_id] = {
            "url": url.strip(),
            "model": provider_model.strip(),
            "token_env": token_env,
        }
    return normalized, None


def _additional_hosts() -> set[str]:
    return {
        value.strip().lower()
        for value in os.environ.get("SZL_MODEL_ALLOWED_HOSTS", "").split(",")
        if value.strip()
    }


def _validated_endpoint(url: str) -> tuple[str | None, str | None]:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None, "endpoint URL could not be parsed"
    host = (parsed.hostname or "").lower()
    if (
        not host
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return None, "endpoint URL contains a prohibited component"

    try:
        port = parsed.port
    except ValueError:
        return None, "endpoint port is invalid"

    local_hosts = {"localhost", "127.0.0.1", "::1"}
    is_local = host in local_hosts
    if is_local:
        if not _flag("SZL_MODEL_ALLOW_LOCAL"):
            return None, "local model endpoints require SZL_MODEL_ALLOW_LOCAL=1"
        if parsed.scheme not in {"http", "https"}:
            return None, "local endpoint must use HTTP or HTTPS"
    else:
        if parsed.scheme != "https":
            return None, "remote model endpoints must use HTTPS"
        hf_host = (
            host == "router.huggingface.co"
            or host.endswith(".endpoints.huggingface.cloud")
        )
        if not hf_host and host not in _additional_hosts():
            return None, "endpoint host is not allowlisted"
        if port not in (None, 443):
            return None, "remote model endpoint must use port 443"

    return url, None


def _is_hugging_face_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return (
        host == "router.huggingface.co"
        or host.endswith(".endpoints.huggingface.cloud")
    )


def _endpoint_for_model(model_id: str) -> tuple[dict[str, Any] | None, str | None]:
    mapping, map_error = _endpoint_map()
    if map_error:
        return None, map_error

    if model_id in mapping:
        configured = mapping[model_id]
        url, url_error = _validated_endpoint(configured["url"])
        if url_error or url is None:
            return None, f"{model_id}: {url_error}"
        token_env = configured["token_env"]
        if not token_env:
            token_env = "HF_TOKEN" if _is_hugging_face_host(url) else "SZL_MODEL_GATEWAY_TOKEN"
        token = os.environ.get(token_env, "").strip()
        if _is_hugging_face_host(url) and not token:
            return None, f"{model_id}: {token_env} is not configured"
        return {
            "url": url,
            "provider_model": configured["model"],
            "token": token,
            "provider": "dedicated_endpoint",
        }, None

    metadata = _OWNED_MODELS[model_id]
    if not metadata["router_eligible"]:
        return None, f"{model_id}: dedicated endpoint required"
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        return None, f"{model_id}: HF_TOKEN is not configured"
    router_url = os.environ.get("SZL_HF_ROUTER_URL", _HF_ROUTER_URL).strip()
    url, url_error = _validated_endpoint(router_url)
    if url_error or url is None:
        return None, f"Hugging Face router: {url_error}"
    if (urlparse(url).hostname or "").lower() != "router.huggingface.co":
        return None, "SZL_HF_ROUTER_URL must remain on router.huggingface.co"
    suffix = os.environ.get("SZL_HF_PROVIDER_SUFFIX", "").strip()
    if suffix and not re.fullmatch(r":[A-Za-z0-9_.-]{1,32}", suffix):
        return None, "SZL_HF_PROVIDER_SUFFIX is invalid"
    return {
        "url": url,
        "provider_model": model_id + suffix,
        "token": token,
        "provider": "huggingface_inference_providers",
    }, None


def _configured_models() -> tuple[list[str], dict[str, str]]:
    configured: list[str] = []
    reasons: dict[str, str] = {}
    for model_id, metadata in _OWNED_MODELS.items():
        if not metadata["callable"]:
            reasons[model_id] = "not callable"
            continue
        spec, error = _endpoint_for_model(model_id)
        if spec is not None:
            configured.append(model_id)
        else:
            reasons[model_id] = error or "not configured"
    return configured, reasons


def _public_model_catalog() -> dict[str, Any]:
    configured, reasons = _configured_models()
    configured_set = set(configured)
    models = []
    for model_id, metadata in _OWNED_MODELS.items():
        item = {"id": model_id, **metadata}
        item["runtime_configured"] = model_id in configured_set
        if model_id not in configured_set:
            item["runtime_reason"] = reasons.get(model_id, "not configured")
        models.append(item)
    return {
        "schema": "szl.hatun.owned-model-registry/v1",
        "observed_at": "2026-10-08",
        "runtime_evidence": "configuration only; invocation required for live proof",
        "models": models,
    }


def _validate_chat_args(args: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(args, dict):
        return None, "arguments must be an object"
    allowed = {"prompt", "messages", "task", "model", "temperature", "max_tokens"}
    unknown = sorted(set(args) - allowed)
    if unknown:
        return None, "unsupported arguments: " + ", ".join(unknown)

    has_prompt = "prompt" in args
    has_messages = "messages" in args
    if has_prompt == has_messages:
        return None, "provide exactly one of prompt or messages"

    if has_prompt:
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return None, "prompt must be a non-empty string"
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
    else:
        raw_messages = args.get("messages")
        if not isinstance(raw_messages, list) or not 1 <= len(raw_messages) <= _MAX_MESSAGE_COUNT:
            return None, f"messages must contain 1 to {_MAX_MESSAGE_COUNT} entries"
        messages = []
        for index, item in enumerate(raw_messages):
            if not isinstance(item, dict):
                return None, f"messages[{index}] must be an object"
            role = item.get("role")
            content = item.get("content")
            if role not in {"system", "user", "assistant"}:
                return None, f"messages[{index}].role is invalid"
            if not isinstance(content, str) or not content:
                return None, f"messages[{index}].content must be a non-empty string"
            messages.append({"role": role, "content": content})

    total_chars = 0
    for index, message in enumerate(messages):
        length = len(message["content"])
        if length > _MAX_SINGLE_MESSAGE_CHARS:
            return None, f"messages[{index}] exceeds {_MAX_SINGLE_MESSAGE_CHARS} characters"
        total_chars += length
    if total_chars > _MAX_MESSAGE_CHARS:
        return None, f"message content exceeds {_MAX_MESSAGE_CHARS} characters"

    task = args.get("task", "general")
    if not isinstance(task, str) or task not in _TASK_DEFAULTS:
        return None, "task is not in the governed routing catalog"

    requested_model = args.get("model")
    if requested_model is not None and (
        not isinstance(requested_model, str) or requested_model not in _OWNED_MODELS
    ):
        return None, "model is not in the SZL owned-model registry"
    if requested_model is not None and not _OWNED_MODELS[requested_model]["callable"]:
        return None, "selected artifact is not a callable generation model"

    temperature = args.get("temperature", 0.2)
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        return None, "temperature must be a number"
    temperature = float(temperature)
    if not 0.0 <= temperature <= 2.0:
        return None, "temperature must be between 0 and 2"

    max_tokens = args.get("max_tokens", 512)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        return None, "max_tokens must be an integer"
    if not 1 <= max_tokens <= 2048:
        return None, "max_tokens must be between 1 and 2048"

    return {
        "messages": messages,
        "task": task,
        "requested_model": requested_model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }, None


def _select_model(
    task: str,
    requested_model: str | None,
) -> tuple[str | None, dict[str, Any] | None, str]:
    if requested_model is not None:
        spec, error = _endpoint_for_model(requested_model)
        if spec is None:
            return None, None, error or "requested model is not configured"
        return requested_model, spec, "explicit_model"

    preferred = _TASK_DEFAULTS[task]
    spec, _ = _endpoint_for_model(preferred)
    if spec is not None:
        return preferred, spec, f"task_default:{task}"

    fallback = "SZLHOLDINGS/SZL-Khipu-1.5B"
    fallback_spec, _ = _endpoint_for_model(fallback)
    if fallback_spec is not None:
        return fallback, fallback_spec, f"task_default_unavailable:{preferred};fallback:grounded_default"

    configured, reasons = _configured_models()
    if configured:
        model_id = configured[0]
        spec, _ = _endpoint_for_model(model_id)
        return model_id, spec, f"task_default_unavailable:{preferred};fallback:first_configured"

    detail = reasons.get(preferred, "no model runtime configured")
    return None, None, detail


async def _read_bounded_response(response: httpx.Response) -> bytes:
    declared = response.headers.get("content-length")
    if declared:
        try:
            if int(declared) > _MAX_RESPONSE_BYTES:
                raise ValueError("MODEL_RESPONSE_TOO_LARGE")
        except ValueError as exc:
            if str(exc) == "MODEL_RESPONSE_TOO_LARGE":
                raise
            raise ValueError("INVALID_MODEL_CONTENT_LENGTH") from None
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > _MAX_RESPONSE_BYTES:
            raise ValueError("MODEL_RESPONSE_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)


def _public_endpoint_label(model_id: str, endpoint_spec: dict[str, Any]) -> str:
    """Return a receipt-safe endpoint label without exposing private endpoint URLs."""
    if endpoint_spec["provider"] == "huggingface_inference_providers":
        return _HF_ROUTER_URL
    return f"configured://{model_id}"


class LlmAdapter(OrganAdapter):
    organ = "llm"
    base_env = "SZL_LLM_URL"
    base_default = "https://a-11-oy.com"
    catalog_route = "/api/a11oy/v1/llm/tiers"

    async def fetch_catalog(self, timeout: float = DEFAULT_TIMEOUT) -> CatalogResult:
        crit = GOVERNANCE_CRITICAL.get("llm", set())
        tools = [
            OrganTool(
                organ="llm",
                name="tiers",
                description=(
                    "List the a11oy open-LLM router tiers (id, rank, use, why) "
                    "from the product route."
                ),
                input_schema={"type": "object", "additionalProperties": False},
                governance_critical="tiers" in crit,
            )
        ]
        reason = (
            "llm_tiers is derived from the a11oy /api/a11oy/v1/llm/tiers route; "
            "the llm organ exposes no JSON /v1/mcp/tools catalog"
        )

        if _owned_models_enabled():
            tools.append(
                OrganTool(
                    organ="llm",
                    name="models",
                    description=(
                        "List the source-bound SZL model registry and disclose which "
                        "runtimes are configured without exposing credentials."
                    ),
                    input_schema={"type": "object", "additionalProperties": False},
                    governance_critical="models" in crit,
                )
            )
            configured, _ = _configured_models()
            if configured:
                tools.append(
                    OrganTool(
                        organ="llm",
                        name="chat",
                        description=(
                            "Run a governed chat request against an allowlisted SZL-owned "
                            "model through Hugging Face or a dedicated endpoint."
                        ),
                        input_schema={
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string"},
                                "messages": {
                                    "type": "array",
                                    "minItems": 1,
                                    "maxItems": _MAX_MESSAGE_COUNT,
                                    "items": {
                                        "type": "object",
                                        "required": ["role", "content"],
                                        "properties": {
                                            "role": {
                                                "type": "string",
                                                "enum": ["system", "user", "assistant"],
                                            },
                                            "content": {"type": "string"},
                                        },
                                        "additionalProperties": False,
                                    },
                                },
                                "task": {
                                    "type": "string",
                                    "enum": sorted(_TASK_DEFAULTS),
                                    "default": "general",
                                },
                                "model": {
                                    "type": "string",
                                    "enum": sorted(
                                        model_id
                                        for model_id, metadata in _OWNED_MODELS.items()
                                        if metadata["callable"]
                                    ),
                                },
                                "temperature": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 2,
                                    "default": 0.2,
                                },
                                "max_tokens": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 2048,
                                    "default": 512,
                                },
                            },
                            "oneOf": [
                                {"required": ["prompt"]},
                                {"required": ["messages"]},
                            ],
                            "additionalProperties": False,
                        },
                        governance_critical="chat" in crit,
                    )
                )
                reason += "; owned model registry and chat runtime are explicitly enabled"
            else:
                reason += "; owned model registry enabled, but no callable runtime is configured"

        return CatalogResult(
            self.organ,
            True,
            tools,
            200,
            self.base_url + self.catalog_route,
            reason=reason,
        )

    def call_routes(self, tool: str) -> list[str]:
        if tool == "tiers":
            return ["/api/a11oy/v1/llm/tiers"]
        return []

    async def _call_tiers(
        self,
        args: dict,
        timeout: float,
    ) -> B.BackendResult:
        url = self.base_url + "/api/a11oy/v1/llm/tiers"
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, params=args or {})
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            return B.BackendResult(
                deployed=False,
                http_status=f"transport_error:{type(exc).__name__}",
                endpoint=url,
                error="route_not_live",
                reason=(
                    f"llm.tiers: GET {url} failed ({type(exc).__name__}). "
                    "Honest stub — disclosed, not faked."
                ),
                data=None,
            )
        if response.status_code == 404:
            return B.BackendResult(
                deployed=False,
                http_status=404,
                endpoint=url,
                error="route_not_live",
                reason=f"llm.tiers: {url} returned 404. Honest stub — disclosed, not faked.",
                data=None,
            )
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError):
            data = {"raw": response.text[:2000]}
        return B.BackendResult(
            deployed=True,
            http_status=response.status_code,
            endpoint=url,
            error=None if response.status_code < 400 else f"http_{response.status_code}",
            data=data,
        )

    async def _call_models(self) -> B.BackendResult:
        if not _owned_models_enabled():
            return B.BackendResult(
                deployed=False,
                http_status=None,
                endpoint="local://szl-owned-model-registry",
                error="owned_models_disabled",
                reason="Set SZL_OWNED_MODELS_ENABLED=1 to expose the governed model registry.",
                data=None,
            )
        return B.BackendResult(
            deployed=True,
            http_status=200,
            endpoint="local://szl-owned-model-registry",
            error=None,
            data=_public_model_catalog(),
        )

    async def _call_chat(
        self,
        args: dict,
        timeout: float,
    ) -> B.BackendResult:
        if not _owned_models_enabled():
            return B.BackendResult(
                deployed=False,
                http_status=None,
                endpoint="local://szl-owned-model-gateway",
                error="owned_models_disabled",
                reason="Set SZL_OWNED_MODELS_ENABLED=1 before model inference.",
                data=None,
            )

        validated, validation_error = _validate_chat_args(args)
        if validated is None:
            return B.BackendResult(
                deployed=False,
                http_status=None,
                endpoint="local://szl-owned-model-gateway",
                error="invalid_arguments",
                reason=validation_error,
                data=None,
            )

        model_id, endpoint_spec, routing_reason = _select_model(
            validated["task"],
            validated["requested_model"],
        )
        if model_id is None or endpoint_spec is None:
            return B.BackendResult(
                deployed=False,
                http_status=None,
                endpoint="local://szl-owned-model-gateway",
                error="model_runtime_not_configured",
                reason=routing_reason,
                data=None,
            )

        headers = {"content-type": "application/json"}
        if endpoint_spec["token"]:
            headers["authorization"] = "Bearer " + endpoint_spec["token"]
        payload = {
            "model": endpoint_spec["provider_model"],
            "messages": validated["messages"],
            "temperature": validated["temperature"],
            "max_tokens": validated["max_tokens"],
            "stream": False,
        }
        url = endpoint_spec["url"]
        endpoint_label = _public_endpoint_label(model_id, endpoint_spec)

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                ) as response:
                    if 300 <= response.status_code < 400:
                        return B.BackendResult(
                            deployed=False,
                            http_status=response.status_code,
                            endpoint=endpoint_label,
                            error="redirect_rejected",
                            reason="Model endpoint redirects are rejected to protect credentials.",
                            data=None,
                        )
                    try:
                        body = await _read_bounded_response(response)
                    except ValueError as exc:
                        return B.BackendResult(
                            deployed=True,
                            http_status=response.status_code,
                            endpoint=endpoint_label,
                            error=str(exc).lower(),
                            reason="Model response exceeded the accepted transport contract.",
                            data=None,
                        )
                    try:
                        provider_response: Any = json.loads(body)
                    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                        provider_response = {
                            "raw": body.decode("utf-8", errors="replace")[:2000]
                        }
                    return B.BackendResult(
                        deployed=True,
                        http_status=response.status_code,
                        endpoint=endpoint_label,
                        error=(
                            None
                            if response.status_code < 400
                            else f"http_{response.status_code}"
                        ),
                        data={
                            "schema": "szl.hatun.owned-model-response/v1",
                            "task": validated["task"],
                            "selected_model": model_id,
                            "routing_reason": routing_reason,
                            "authority": _OWNED_MODELS[model_id]["authority"],
                            "provider": endpoint_spec["provider"],
                            "response": provider_response,
                        },
                    )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            return B.BackendResult(
                deployed=False,
                http_status=f"transport_error:{type(exc).__name__}",
                endpoint=endpoint_label,
                error="model_transport_error",
                reason=f"Model endpoint transport failed: {type(exc).__name__}.",
                data=None,
            )

    async def call(
        self,
        tool: str,
        args: dict,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> B.BackendResult:
        if tool == "tiers":
            return await self._call_tiers(args, timeout)
        if tool == "models":
            return await self._call_models()
        if tool == "chat":
            return await self._call_chat(args, timeout)
        return B.BackendResult(
            deployed=False,
            http_status=None,
            endpoint=self.base_url,
            error="unknown_tool",
            reason=f"llm.{tool} is not an allowlisted Hatun model tool.",
            data=None,
        )
