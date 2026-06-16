# DEPRECATED — old → new mapping (2026-06-16)

The three previously-codenamed backend Spaces were **purged** (every old route now
returns HTTP 404). Hatun-MCP was repointed to the **live honest a11oy organs** on
`a11oy.net` (each verified **200** before wiring), and the two user-visible tool
names that carried a codename were renamed to honest organ names.

## Renamed MCP tools

| Old tool name (REMOVED — not served) | New tool name | Backend (live, verified 200) |
|--------------------------------------|---------------|------------------------------|
| `szl_sentra_scan` | **`szl_immune_scan`** | `POST /api/a11oy/v1/immune/verdict` (the immune *screen* is the signed verdict route) |
| `szl_rosie_reason` | **`szl_companion_reason`** | `POST /api/a11oy/v1/companion/ask` |

> **Back-compat decision.** The old codename names are **not** registered in
> `tools/list`. Per SZL doctrine, no user-visible codename may appear in tool names,
> the server-card, the README, or any served string — so re-registering the old
> names as live aliases (which would re-expose the codename in `tools/list`) is
> **not** done. This document is the canonical migration map. Consumers still on the
> old names must switch to the new names above; the call signatures are unchanged.
>
> Two honest a11oy-named twins remain available and route to the SAME live backend:
> `szl_a11oy_sentinel_scan` (= `szl_immune_scan`) and
> `szl_a11oy_operator_reason` (= `szl_companion_reason`).

## Renamed adapters / organ ids

| Old adapter / organ id | New adapter / organ id | Catalog route (live) | Action route(s) (live) |
|------------------------|------------------------|----------------------|------------------------|
| `sentra` (`SentraAdapter`) | **`immune`** (`ImmuneAdapter`) | `GET /api/a11oy/v1/immune/gates` (200) | `GET\|POST /api/a11oy/v1/immune/verdict` (200) |
| `rosie` (`RosieAdapter`) | **`companion`** (`CompanionAdapter`) | (no JSON catalog) | `POST /api/a11oy/v1/companion/ask` (200), `POST /companion/act` (200), `GET /companion/recommend` (200) |
| `amaru` (`AmaruAdapter`) | **`llm`** (`LlmAdapter`) | `GET /api/a11oy/v1/llm/tiers` (200) | `GET /api/a11oy/v1/llm/tiers` (200) |

## Routes that do NOT exist (mapped to closest real route — never pointed at a 404)

- `/api/a11oy/v1/immune/screen` → **404**. The immune *screen* IS the signed
  `/api/a11oy/v1/immune/verdict` route (live 200); the `screen` tool maps there.
- `/api/a11oy/v1/immune/inspect` → **404** (same as above).

## Dynamic organ-tool names

Service-derived tools are now named `immune_*`, `companion_*`, `llm_*` (and the
unchanged `killinchu_*`, `a11oy_*`). No `sentra_*` / `rosie_*` / `amaru_*` tool name
is ever emitted.
