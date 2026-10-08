# SZL-owned model runtime for Hatun MCP

Status: implementation proposal in code. It is **opt-in**, fail-closed, and does
not claim that any model is currently deployed or benchmark-qualified.

## Why this path

SZL already has useful model artifacts. The shortest path to actual product use
is not another showcase. It is a governed inference path:

`client -> Hatun MCP -> Yuyay policy -> SZL model endpoint -> Khipu receipt -> DSSE response`

That uses existing SZL software instead of bypassing it:

- **Hatun MCP** is the client-facing tool plane.
- **A11oy/Alloy** supplies policy and product routing.
- **Yuyay** gates the request.
- **Khipu** records the evidence receipt.
- **Hugging Face or a private endpoint** supplies model compute.
- **a-11-oy.com** can expose the product experience after runtime proof.
- **a11oy.net** can publish bounded release evidence after independent readback.

## Initial governed model registry

The code contains a source-bound registry refreshed from public Hub metadata on
2026-10-08. Metadata is not runtime proof.

| Model | Intended use | Serving path | Authority boundary |
|---|---|---|---|
| `SZLHOLDINGS/SZL-Khipu-1.5B` | grounded generation, retrieval synthesis | HF Inference Providers or dedicated endpoint | advisory, grounded-only |
| `SZLHOLDINGS/chaski` | proposals and research assistance | HF Inference Providers or dedicated endpoint | proposal-only |
| `SZLHOLDINGS/WILLAY` | identity and doctrine assistance | dedicated endpoint; PEFT adapter | advisory |
| `SZLHOLDINGS/brain-navigator-r2` | research navigation | dedicated endpoint; PEFT adapter | proposal-only |
| `SZLHOLDINGS/szl-triage-qwen3.5-0.8b-lora-study5` | experimental structured triage | dedicated endpoint; PEFT adapter | experimental advisory |
| `SZLHOLDINGS/A11OY-MINI` | local/offline generation | llama.cpp or dedicated endpoint | advisory |
| `SZLHOLDINGS/MiniEmbed-Nano` | reference fixture and evaluation | not exposed for generation | test fixture only |

## MCP tools

The existing `llm_tiers` behavior is unchanged by default.

Set:

```text
SZL_OWNED_MODELS_ENABLED=1
```

to expose:

- `llm_models`: lists the registry and runtime-configuration state. It never
  returns credential values.
- `llm_chat`: appears only when at least one callable runtime is configured.
  Requests are allowlisted, size-bounded, non-streaming, and cannot supply an
  arbitrary endpoint.

## Fastest first deployment

Start with `SZLHOLDINGS/SZL-Khipu-1.5B` as the default governed model.

### Option A: Hugging Face Inference Providers

```text
SZL_OWNED_MODELS_ENABLED=1
HF_TOKEN=<runtime secret>
```

Hatun calls the official OpenAI-compatible router:

```text
https://router.huggingface.co/v1/chat/completions
```

This is attempted only for registry entries explicitly marked router-eligible.
Provider availability is discovered by the real invocation; an endpoint-
compatible model card is not treated as proof that a provider currently serves
the model.

Optional provider selection:

```text
SZL_HF_PROVIDER_SUFFIX=:preferred
```

### Option B: dedicated or self-hosted endpoint

Use this for PEFT adapters, A11OY-MINI, private endpoints, or predictable
capacity. Each value is a complete OpenAI-compatible chat-completions URL.

```text
SZL_OWNED_MODELS_ENABLED=1
SZL_MODEL_ALLOWED_HOSTS=models.example.com
SZL_MODEL_GATEWAY_TOKEN=<runtime secret>
SZL_MODEL_ENDPOINTS_JSON={
  "SZLHOLDINGS/WILLAY": {
    "url": "https://models.example.com/willay/v1/chat/completions",
    "model": "willay"
  },
  "SZLHOLDINGS/brain-navigator-r2": {
    "url": "https://models.example.com/brain/v1/chat/completions",
    "model": "brain-navigator-r2"
  }
}
```

For a Hugging Face dedicated endpoint, the default credential is `HF_TOKEN`. A
mapping can name a different uppercase environment variable through
`token_env`.

For a local llama.cpp server:

```text
SZL_OWNED_MODELS_ENABLED=1
SZL_MODEL_ALLOW_LOCAL=1
SZL_MODEL_ENDPOINTS_JSON={
  "SZLHOLDINGS/A11OY-MINI": {
    "url": "http://127.0.0.1:8080/v1/chat/completions",
    "model": "a11oy-mini"
  }
}
```

Do not expose a local endpoint directly to the public Internet. Put it behind the
existing authenticated Hatun/A11oy control plane.

## Security properties

- Owned-model functionality is disabled unless explicitly enabled.
- Only registry model IDs are callable.
- Clients cannot submit an endpoint URL or credential.
- Remote endpoints must use HTTPS and an explicit host allowlist.
- Local HTTP requires a separate opt-in flag.
- The Hugging Face token is sent only to Hugging Face router/endpoint hosts.
- A separate gateway token is used for non-Hugging-Face hosts.
- Redirects are rejected.
- Inputs and outputs are bounded.
- Model errors remain errors; no response or metric is fabricated.
- Endpoint URLs for dedicated services are replaced by receipt-safe labels.
- Model output is advisory and remains subject to Hatun governance and receipts.

## Routing behavior

A caller may select a governed task, such as `grounded`, `proposal`, `identity`,
`navigation`, or `triage`. Hatun selects the intended model when its runtime is
configured. If an implicit task-specific runtime is unavailable, it may fall
back to Khipu and records that fallback in the response. An explicitly requested
model never silently falls back.

## Release gates

Before production activation:

1. Run the full Hatun test suite.
2. Deploy one private Khipu endpoint or validate provider routing.
3. Add the variables and secrets in the runtime control plane; never commit them.
4. Exercise `tools/list`, `llm_models`, and a bounded `llm_chat` call.
5. Verify Yuyay decision, Khipu receipt, DSSE envelope, model identity, latency,
   token accounting, and failure behavior.
6. Perform prompt-injection, tenant-isolation, redirect, replay, timeout, and
   oversized-response tests.
7. Canary the product route.
8. Publish exact source revision and bounded runtime evidence to a11oy.net only
   after independent readback.

## Recommended product sequence

1. Khipu grounded answer service.
2. Retrieval over commercially eligible SZL datasets with citations.
3. Brain Navigator research workflow.
4. WILLAY doctrine assistant.
5. Triage as an experimental, human-reviewed classifier.
6. Chaski proposal/multimodal work after its evaluation boundary is explicit.
7. A11OY-MINI as an offline/private option.

This sequence turns the estate into one usable system rather than presenting a
collection of disconnected model cards.
