"""Versioned formula call binding and independent, trusted-key verification.

This is a Python JSON profile, not RFC 8785/JCS or a replay-protection service.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

SCHEMA = "urn:szl:hatun:formula-call-binding:v1"
CANONICALIZATION = "python-json-finite-v1"
PAYLOAD_TYPE = "application/vnd.szl.hatun-mcp.response+json"
TOOL = "szl_formula_evaluate"
OPERATION = "formula.evaluate"
_CHALLENGE = re.compile(r"[A-Za-z0-9_-]{22,128}\Z")


def canonical_bytes(value: Any) -> bytes:
    """Finite JSON only; preserve integer/float distinctions and own string keys.

    Keys sort by Unicode code point, ASCII escaping uses Python json's spelling,
    and numbers use Python json's representation. This profile is explicitly
    separate from JCS; consumers must implement this profile or use this verifier.
    """
    def check(item):
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                check(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                check(child)
            return
        raise ValueError("formula binding requires finite JSON with string keys")

    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(domain: str, value: Any) -> str:
    return hashlib.sha256((SCHEMA + "\0" + domain + "\0").encode("ascii")
                          + canonical_bytes(value)).hexdigest()


def formula_request(name: str, args: dict | None, challenge: str | None) -> dict:
    """Snapshot the effective call, including an optional caller-owned challenge."""
    if type(name) is not str or (args is not None and type(args) is not dict):
        raise ValueError("invalid formula request")
    if challenge is not None and (type(challenge) is not str
                                  or not _CHALLENGE.fullmatch(challenge)):
        raise ValueError("receipt_challenge must be 22-128 base64url characters")
    return json.loads(canonical_bytes({"tool": TOOL, "operation_id": OPERATION,
                                      "name": name, "args": {} if args is None else args,
                                      "receipt_challenge": challenge}))


def bind_formula_call(request: dict, response: dict) -> dict:
    return {"schema": SCHEMA, "canonicalization": CANONICALIZATION,
            "algorithm": "sha256", "request_digest": _digest("request", request),
            "response_digest": _digest("response", response)}


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate receipt JSON member")
        value[key] = item
    return value


def _invalid_constant(_):
    raise ValueError("non-finite receipt JSON")


def verify_formula_response(response: dict, *, trusted_public_key_pem: bytes,
                            expected_client_id: str, name: str,
                            args: dict | None = None,
                            receipt_challenge: str | None = None) -> dict:
    """Verify signature, receipt hash, expected operator and exact formula output.

    The public key must be trusted separately; do not learn it from the response.
    A caller that requires a pending-request challenge must pass its saved value.
    Reusing that challenge permits replay; this function maintains no replay store.
    Returns the signed receipt packet on success and raises ValueError otherwise.
    """
    try:
        if type(response) is not dict or not expected_client_id:
            raise ValueError("invalid verification input")
        key = serialization.load_pem_public_key(trusted_public_key_pem)
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError("trusted key must use P-256")
        env = response["dsse"]
        if env["payloadType"] != PAYLOAD_TYPE or len(env["signatures"]) != 1:
            raise ValueError("invalid signed envelope")
        payload = base64.b64decode(env["payload"], validate=True)
        signature = base64.b64decode(env["signatures"][0]["sig"], validate=True)
        payload_type = PAYLOAD_TYPE.encode("utf-8")
        pae = (b"DSSEv1 " + str(len(payload_type)).encode() + b" " + payload_type
               + b" " + str(len(payload)).encode() + b" " + payload)
        key.verify(signature, pae, ec.ECDSA(hashes.SHA256()))
        signed = json.loads(payload, object_pairs_hook=_unique_object,
                            parse_constant=_invalid_constant)
        packet = signed["receipt"]
        digest = hashlib.sha256(canonical_bytes(packet)).hexdigest()
        if not hmac.compare_digest(digest, signed["continuum_hash"]):
            raise ValueError("invalid receipt hash")
        rc = response["khipu_receipt"]
        if any(canonical_bytes(rc[field]) != canonical_bytes(packet[field]) for field in (
            "receipt_id", "prev_hash", "tripwire", "puriq_score", "hatun_mcp_factor"
        )) or rc["continuum_hash"] != digest:
            raise ValueError("response receipt mismatch")
        if (packet["tool"] != TOOL or packet["operation_id"] != OPERATION
                or packet["client_id"] != expected_client_id
                or response["tool"] != TOOL or response["status"] != packet["status"]):
            raise ValueError("unexpected receipt identity")
        projection = {field: response[field] for field in ("tool", "status", "data", "backend")}
        expected = bind_formula_call(formula_request(name, args, receipt_challenge), projection)
        if packet["detail"]["formula_call_binding"] != expected:
            raise ValueError("formula request or response mismatch")
        return packet
    except Exception as exc:
        # Never reflect input, signature bytes or key material in a verifier error.
        raise ValueError("formula receipt verification failed") from exc
