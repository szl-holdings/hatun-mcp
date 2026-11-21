"""Offline approval-intent and stale-file witness (NO execution authority).

Independent contract reference: Pydantic AI v2.71.0 (MIT), validated_args and
stale-file detection. This is original SZL code and does not import or launch
Pydantic AI or any real tool. An unkeyed hash is NOT an approval signature.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

MAX_ARGS_BYTES = 16 * 1024
MAX_FILE_BYTES = 128 * 1024
MAX_FILES = 8
MAX_TOTAL_FILE_BYTES = 512 * 1024
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
ACTION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


class IntentError(ValueError):
    """The proposed action or evidence is unsafe or ill-formed."""


def _canonical(value: Any) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         allow_nan=False).encode("ascii")
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise IntentError("NON_CANONICAL_JSON_ARGUMENTS") from None
    if len(raw) > MAX_ARGS_BYTES:
        raise IntentError("ARGS_TOO_LARGE")
    return raw


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _validate_action(action: str, args: dict[str, Any]) -> None:
    if not isinstance(action, str) or not ACTION_NAME.fullmatch(action):
        raise IntentError("INVALID_ACTION_NAME")
    if not isinstance(args, dict) or not all(isinstance(k, str) for k in args):
        raise IntentError("INVALID_ACTION_ARGS")
    _canonical(args)


def _read_files(root: Path, filenames: list[str]) -> list[dict[str, Any]]:
    if (not isinstance(filenames, list) or not 0 <= len(filenames) <= MAX_FILES or
            any(not isinstance(name, str) or not FILE_NAME.fullmatch(name) for name in filenames) or
            len(set(filenames)) != len(filenames)):
        raise IntentError("INVALID_ARTIFACT_SELECTION")
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        raise IntentError("INVALID_WORKSPACE_ROOT") from None
    if not root.is_dir():
        raise IntentError("INVALID_WORKSPACE_ROOT")
    result: list[dict[str, Any]] = []
    total = 0
    for name in sorted(filenames):
        path = root / name
        if path.is_symlink():
            raise IntentError("ARTIFACT_SYMLINK_NOT_ALLOWED")
        try:
            target = path.resolve(strict=True)
            if not target.is_relative_to(root) or not target.is_file():
                raise IntentError("ARTIFACT_OUTSIDE_WORKSPACE")
            with target.open("rb") as fd:
                raw = fd.read(MAX_FILE_BYTES + 1)
        except (OSError, RuntimeError):
            raise IntentError("ARTIFACT_MISSING_OR_UNREADABLE") from None
        if len(raw) > MAX_FILE_BYTES:
            raise IntentError("ARTIFACT_TOO_LARGE")
        total += len(raw)
        if total > MAX_TOTAL_FILE_BYTES:
            raise IntentError("ARTIFACT_AGGREGATE_TOO_LARGE")
        result.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return result


def snapshot_proposal(action: str, args: dict[str, Any], root: Path,
                      filenames: list[str]) -> dict[str, Any]:
    """Capture exactly what was proposed, not who approved it or the right to run."""
    _validate_action(action, args)
    artifacts = _read_files(root, filenames)
    envelope: dict[str, Any] = {
        "schema": "szl.hatun.deferred-intent-witness/v1",
        "action": action,
        "validated_args_sha256": _hash(args),
        "artifacts": artifacts,
        "approval_verified": False,
        "tool_execution_authority": "NONE",
    }
    envelope["witness_sha256"] = _hash(envelope)
    return envelope


def recheck_proposal(witness: dict[str, Any], action: str, args: dict[str, Any],
                     root: Path) -> dict[str, Any]:
    """Return deterministic DENY or UNCHANGED_UNAUTHORIZED; never execute.

    The witness can be modified/resealed by any party. Its unkeyed digest proves
    only internal byte consistency. A production wrapper needs authenticated
    approval binding AND race-free file execution after this check.
    """
    if not isinstance(witness, dict) or set(witness) != {
        "schema", "action", "validated_args_sha256", "artifacts",
        "approval_verified", "tool_execution_authority", "witness_sha256",
    }:
        return {"status": "DENY", "reason": "INVALID_WITNESS_SHAPE"}
    if (witness["schema"] != "szl.hatun.deferred-intent-witness/v1" or
            witness["approval_verified"] is not False or
            witness["tool_execution_authority"] != "NONE"):
        return {"status": "DENY", "reason": "INVALID_AUTHORITY_CLAIM"}
    try:
        claimed = witness["witness_sha256"]
        if not isinstance(claimed, str) or not SHA.fullmatch(claimed):
            raise IntentError("INVALID_WITNESS_DIGEST")
        if _hash({k: v for k, v in witness.items() if k != "witness_sha256"}) != claimed:
            raise IntentError("WITNESS_BYTES_CHANGED")
        _validate_action(action, args)
        if action != witness["action"] or _hash(args) != witness["validated_args_sha256"]:
            raise IntentError("ACTION_OR_ARGUMENTS_CHANGED")
        old = witness["artifacts"]
        if (not isinstance(old, list) or len(old) > MAX_FILES or
                any(not isinstance(x, dict) or set(x) != {"path", "bytes", "sha256"}
                    or type(x["bytes"]) is not int or not 0 <= x["bytes"] <= MAX_FILE_BYTES
                    or not isinstance(x["sha256"], str) or not SHA.fullmatch(x["sha256"])
                    for x in old)):
            raise IntentError("INVALID_WITNESS_ARTIFACTS")
        fresh = _read_files(root, [x["path"] for x in old])
        if fresh != old:
            raise IntentError("STALE_ARTIFACT")
    except IntentError as exc:
        return {"status": "DENY", "reason": str(exc)}
    return {"status": "UNCHANGED_UNAUTHORIZED", "reason": "APPROVAL_NOT_VERIFIED",
            "witness_sha256": claimed, "tool_execution_authority": "NONE"}
