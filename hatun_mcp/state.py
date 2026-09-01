"""
hatun_mcp.state — the ONE real-data source behind the human console.

Everything in here is read out of THIS running process at request time:

  * the tool catalogue is enumerated from the live FastMCP tool registry
    (``mcp._tool_manager.list_tools()``), not from a hand-written list — so the
    console shows the tools the server actually exposes right now, including any
    dynamically registered organ tools.
  * the Khipu receipt depth / head hash come from the live append-only chain.
  * signer state, protocol revision, build revision and readiness are read from
    the same singletons the MCP transport uses.

HONESTY RULES enforced here (Doctrine v11):
  * no seeded numbers, no last-known-good values, no interpolation. If a value
    cannot be read, the field carries the honest label ``UNAVAILABLE`` (or
    ``STRUCTURAL-ONLY`` where only the shape is known) and no number.
  * signing state is ``SIGNED`` only when a real ECDSA P-256 key is loaded in
    this process; otherwise ``UNSIGNED``.
  * parity between the published server card and the runtime registry is
    reported as measured, never assumed.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import os
import platform
import time
from datetime import datetime, timezone
from typing import Any

UNAVAILABLE = "UNAVAILABLE"
STRUCTURAL_ONLY = "STRUCTURAL-ONLY"

# Real process start, captured once at import. Uptime is measured against it.
_PROCESS_START_MONOTONIC = time.monotonic()
_PROCESS_START_WALL = time.time()


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def _first_line(text: str | None) -> str:
    """First paragraph line of a docstring — the tool's one-line description."""
    if not text:
        return ""
    for line in text.strip().splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _observed_revision() -> tuple[str, str | None]:
    revision = os.environ.get("SZL_GIT_SHA", "").strip().lower()
    observed = len(revision) == 40 and all(
        character in "0123456789abcdef" for character in revision
    )
    return ("OBSERVED", revision) if observed else (UNAVAILABLE, None)


def _tool_family(name: str) -> str:
    """Group tools by their real registered-name prefix (no editorial guessing)."""
    if name.startswith("szl_"):
        return "szl"
    if name.startswith(("khipu_", "dsse_", "mesh_", "puriq_", "yuyay_", "governance_")):
        return "governance"
    return "organ"


def _tool_rows(mcp: Any) -> tuple[list[dict], str]:
    """Enumerate the LIVE FastMCP tool registry. Returns (rows, state)."""
    try:
        listed = mcp._tool_manager.list_tools()
    except Exception:
        return [], UNAVAILABLE
    rows: list[dict] = []
    for tool in listed:
        schema = getattr(tool, "parameters", None) or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required = schema.get("required", []) if isinstance(schema, dict) else []
        rows.append(
            {
                "name": tool.name,
                "description": _first_line(getattr(tool, "description", "")),
                "family": _tool_family(tool.name),
                "parameters_total": len(properties),
                "parameters_required": len(required),
                "parameter_names": sorted(properties.keys()),
                "is_async": bool(getattr(tool, "is_async", False)),
            }
        )
    rows.sort(key=lambda row: row["name"])
    return rows, "MEASURED"


def _resource_rows(mcp: Any) -> tuple[list[dict], str]:
    try:
        listed = mcp._resource_manager.list_resources()
    except Exception:
        return [], UNAVAILABLE
    rows = [
        {
            "uri": str(getattr(resource, "uri", "")),
            "description": _first_line(getattr(resource, "description", "")),
        }
        for resource in listed
    ]
    rows.sort(key=lambda row: row["uri"])
    return rows, "MEASURED"


def _parity(runtime_names: list[str], card_names: list[str], state: str) -> dict:
    """Measured parity between the published card and the runtime registry."""
    if state != "MEASURED":
        return {
            "state": UNAVAILABLE,
            "runtime_tool_count": None,
            "card_tool_count": len(card_names),
            "only_in_runtime": [],
            "only_in_card": [],
        }
    runtime = set(runtime_names)
    card = set(card_names)
    only_runtime = sorted(runtime - card)
    only_card = sorted(card - runtime)
    return {
        "state": "MATCH" if not only_runtime and not only_card else "DIVERGENT",
        "runtime_tool_count": len(runtime_names),
        "card_tool_count": len(card_names),
        "only_in_runtime": only_runtime,
        "only_in_card": only_card,
    }


def _organ_registration(summary: Any) -> dict:
    """Report dynamic organ-tool registration exactly as the process left it."""
    disabled = os.environ.get("HATUN_MCP_DISABLE_DYNAMIC", "false").lower() == "true"
    if disabled:
        return {"state": "DISABLED", "detail": "HATUN_MCP_DISABLE_DYNAMIC=true",
                "organs": []}
    if not isinstance(summary, dict) or not summary:
        return {"state": UNAVAILABLE, "detail": None, "organs": []}
    if "_error" in summary:
        return {"state": UNAVAILABLE, "detail": str(summary["_error"]), "organs": []}
    organs = []
    for organ, value in sorted(summary.items()):
        if organ.startswith("_"):
            continue
        count = value.get("tools") if isinstance(value, dict) else value
        reachable = value.get("reachable") if isinstance(value, dict) else None
        organs.append(
            {
                "organ": organ,
                "tools_registered": count if isinstance(count, int) else None,
                "reachability": (
                    "REACHED" if reachable is True
                    else UNAVAILABLE if reachable is False
                    else STRUCTURAL_ONLY
                ),
            }
        )
    return {"state": "MEASURED", "detail": None, "organs": organs}


def console_state(*, mcp: Any, khipu: Any, signer: Any, doctrine: dict,
                  organ_summary: Any = None, public_base: str = "") -> dict:
    """Assemble the console payload from live process state only."""
    tools, tools_state = _tool_rows(mcp)
    resources, resources_state = _resource_rows(mcp)
    card_names = card_tool_names()
    build_state, revision = _observed_revision()

    try:
        chain_verified = bool(khipu.verify())
        chain_state = "VERIFIED" if chain_verified else "FAILED"
        depth = khipu.depth()
        head = khipu.head_hash()
    except Exception:
        chain_verified, chain_state, depth, head = False, UNAVAILABLE, None, None

    signer_mode = getattr(signer, "mode", UNAVAILABLE)
    signed = signer_mode == "ECDSA-P256"
    signer_ready = signer_mode != "PLACEHOLDER"
    ready = bool(chain_verified and signer_ready)

    families: dict[str, int] = {}
    for row in tools:
        families[row["family"]] = families.get(row["family"], 0) + 1

    return {
        "service": "hatun-mcp",
        "generated_at": _iso(time.time()),
        "read": "IN-REQUEST",
        "runtime": {
            "transport": "streamable-http",
            "protocol_revision": doctrine["protocol_revision"],
            "python": platform.python_version(),
            "started_at": _iso(_PROCESS_START_WALL),
            "uptime_seconds": round(time.monotonic() - _PROCESS_START_MONOTONIC, 1),
        },
        "build": {"state": build_state, "revision": revision},
        "health": {
            "status": "ok",
            "receipt_chain": chain_state,
            "readiness": "READY" if ready else "NOT-READY",
        },
        "signing": {
            "signer_mode": signer_mode,
            "state": "SIGNED" if signed else "UNSIGNED",
            "algorithm": "ECDSA-P256" if signed else None,
            "transparency_log": UNAVAILABLE,
            "public_key": f"{public_base}/pubkey" if public_base else "/pubkey",
        },
        "khipu": {
            "chain": chain_state,
            "receipts_this_process": depth,
            "head_hash": head,
            "genesis": depth == 0 if isinstance(depth, int) else None,
            "link": "HASH-LINKED",
        },
        "tools": {
            "state": tools_state,
            "count": len(tools) if tools_state == "MEASURED" else None,
            "source": "live FastMCP tool registry (this process)",
            "families": families,
            "items": tools,
        },
        "resources": {
            "state": resources_state,
            "count": len(resources) if resources_state == "MEASURED" else None,
            "items": resources,
        },
        "card_parity": _parity([row["name"] for row in tools], card_names,
                               tools_state),
        "organs": _organ_registration(organ_summary),
        "doctrine": {
            "lean_declarations": doctrine["lean_declarations"],
            "lean_axioms_unique": doctrine["lean_axioms_unique"],
            "lean_sorries_total": doctrine["lean_sorries_total"],
            "yuyay_axes": doctrine["yuyay_axes"],
            "slsa": doctrine["slsa"],
            "lambda": "Conjecture 1 · not a theorem",
            "measured_sha": doctrine["lean_measured_sha"],
        },
    }


# Set by server_http at import so the parity check reads the exact published card.
_CARD_TOOL_NAMES: list[str] = []


def set_card_tool_names(names: list[str]) -> None:
    """Register the published server-card tool names for the parity measurement."""
    global _CARD_TOOL_NAMES
    _CARD_TOOL_NAMES = sorted(names)


def card_tool_names() -> list[str]:
    return list(_CARD_TOOL_NAMES)
