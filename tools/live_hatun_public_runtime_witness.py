#!/usr/bin/env python3
"""Bounded credential-free Hatun public runtime admission witness.

Source-bound public HTTP observations only: NEVER a substitute for authenticated
MCP tools/list + allowlisted tools/call, verified DSSE signer trust root,
operator lease, deployment provenance or normal release approval.

No operator credentials, environment proxy forwarding, HTTP POST, remote writes,
private key reads, model inference, provider jobs, scheduling, or retries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "szl.hatun.public-runtime-admission-witness/v1"
CANONICAL_ORIGIN = "https://mcp.a-11-oy.com"
SOURCE_REPOSITORY = "szl-holdings/hatun-mcp"
SOURCE_MAIN_AT_REVIEW = "1cec84742e07c151a34c329ae2fb50dd5f87c7ab"
MAX_BODY_BYTES = 65536
TIMEOUT_SECONDS = 6
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ROUTES = (
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("GET", "/api/build-info"),
    ("HEAD", "/mcp/"),
)


class PublicWitnessHold(ValueError):
    """Unverifiable or unsafe public observation."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fileobj, code, message, headers, new_url):
        return None


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PublicWitnessHold("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_nonfinite(_value):
    raise PublicWitnessHold("NONFINITE_JSON")


def strict_json(raw: bytes):
    if len(raw) > MAX_BODY_BYTES:
        raise PublicWitnessHold("RESPONSE_BYTE_BUDGET")
    try:
        result = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PublicWitnessHold("INVALID_JSON") from exc
    if type(result) is not dict:
        raise PublicWitnessHold("NOT_A_JSON_OBJECT")
    return result


def fetch_public(method: str, path: str, *, opener=None):
    """Exactly the fixed four public requests. No credential or proxy forwarding."""
    if (method, path) not in ROUTES:
        raise PublicWitnessHold("REQUEST_NOT_ALLOWLISTED")
    url = CANONICAL_ORIGIN + path
    opener = opener or urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()
    )
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "Accept": "application/json",
            "User-Agent": "SZL-public-Hatun-operator-witness/1.0",
        },
    )
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        content_type = exc.headers.get("Content-Type", "")
        raw = exc.read(MAX_BODY_BYTES + 1)
    except (OSError, TimeoutError) as exc:
        raise PublicWitnessHold("PUBLIC_TRANSPORT_UNAVAILABLE") from exc
    if len(raw) > MAX_BODY_BYTES:
        raise PublicWitnessHold("RESPONSE_BYTE_BUDGET")
    if type(status) is not int or not 100 <= status <= 599:
        raise PublicWitnessHold("HTTP_STATUS_UNSUPPORTED")
    if 300 <= status <= 399:
        raise PublicWitnessHold("REDIRECT_NOT_ALLOWED")
    return {"status": status, "content_type": content_type, "raw": raw}


def _safe_body(response, *, route):
    content_type = response.get("content_type")
    if type(content_type) is not str or not content_type.lower().startswith(
        "application/json"
    ):
        raise PublicWitnessHold("JSON_CONTENT_TYPE_UNAVAILABLE")
    try:
        return strict_json(response.get("raw", b""))
    except PublicWitnessHold as exc:
        raise PublicWitnessHold(route + "_JSON_" + str(exc)) from exc


def check_observations(observations, *, expected_source: str):
    """Assess all four observed public surfaces, never authorize production."""
    if type(expected_source) is not str or _SHA40.fullmatch(expected_source) is None:
        raise PublicWitnessHold("EXPECTED_SOURCE_SHA_INVALID")
    if type(observations) is not dict or set(observations) != set(ROUTES):
        raise PublicWitnessHold("OBSERVATION_SET_INVALID")
    reasons = []

    def reason(code):
        if code not in reasons:
            reasons.append(code)

    raw_health = observations[("GET", "/healthz")]
    raw_ready = observations[("GET", "/readyz")]
    raw_build = observations[("GET", "/api/build-info")]
    raw_mcp = observations[("HEAD", "/mcp/")]

    for item in observations.values():
        if type(item) is not dict or type(item.get("status")) is not int:
            raise PublicWitnessHold("OBSERVATION_ROW_INVALID")

    health = _safe_body(raw_health, route="HEALTH")
    ready = _safe_body(raw_ready, route="READY")
    build = _safe_body(raw_build, route="BUILD")

    health_ok = (
        raw_health["status"] == 200
        and health.get("status") == "ok"
        and health.get("service") == "hatun-mcp"
        and health.get("chain_verified") is True
    )
    if not health_ok:
        reason("HEALTHZ_UNAVAILABLE")

    checks = ready.get("checks")
    if type(checks) is not dict:
        checks = {}
    ready_flag = (
        raw_ready["status"] == 200
        and ready.get("ready") is True
        and ready.get("status") == "ready"
        and checks.get("receipt_chain") == "VERIFIED"
        and checks.get("signer") == "CONFIGURED"
        and checks.get("authentication") == "CONFIGURED"
        and ready.get("signer_mode") == "ECDSA-P256"
    )
    if not ready_flag:
        reason("READYZ_NOT_ADMITTED")
    if checks.get("authentication") != "CONFIGURED":
        reason("OPERATOR_AUTH_BINDING_UNAVAILABLE")
    if checks.get("signer") != "CONFIGURED":
        reason("RUNTIME_SIGNER_NOT_CONFIGURED")
    if checks.get("receipt_chain") != "VERIFIED":
        reason("RECEIPT_CHAIN_NOT_VERIFIED")

    deployed = build.get("build")
    revision = deployed.get("revision") if type(deployed) is dict else None
    if (
        raw_build["status"] != 200
        or type(revision) is not str
        or _SHA40.fullmatch(revision) is None
        or revision != expected_source
    ):
        reason("DEPLOYED_SOURCE_REVISION_NOT_ADMITTED")

    # HTTP denial to an anonymous caller is NOT proof that an authenticated
    # caller exists, can list tools, or has a validated DSSE trust root.
    anonymous_denied = raw_mcp["status"] in (401, 403)
    if not anonymous_denied:
        reason("MCP_UNAUTHENTICATED_DENIAL_NOT_PROVEN")
    if raw_mcp["status"] == 200:
        reason("MCP_ANONYMOUS_SURFACE_POSSIBLE")
    elif raw_mcp["status"] == 402:
        reason("MCP_PAYMENT_GATE_OBSERVED_NOT_OPERATOR_AUTH")

    # These are deliberately unprovable from unauthenticated public GETs.
    reason("AUTHENTICATED_MCP_OPERATOR_WITNESS_REQUIRED")
    reason("INDEPENDENT_DSSE_TRUST_ROOT_REQUIRED")
    reason("OWNER_DEPLOYMENT_ADMISSION_REQUIRED")

    return {
        "schema": SCHEMA,
        "state": "HOLD",
        "reasons": sorted(reasons),
        "expected_source_sha": expected_source,
        "observed_build_sha": revision if type(revision) is str else None,
        "liveness_http": raw_health["status"],
        "readiness_http": raw_ready["status"],
        "build_info_http": raw_build["status"],
        "anonymous_mcp_head_http": raw_mcp["status"],
        "liveness_observed": health_ok,
        "release_readiness_self_reported": ready_flag,
        "anonymous_denial_observed": anonymous_denied,
        "signer_mode_label": ready.get("signer_mode")
        if type(ready.get("signer_mode")) is str
        else None,
        "authentication_check": checks.get("authentication")
        if type(checks.get("authentication")) is str
        else None,
        "chain_check": checks.get("receipt_chain")
        if type(checks.get("receipt_chain")) is str
        else None,
        "operator_authenticated_tools_list_verified": False,
        "independent_dsse_signature_verified": False,
        "source_image_attestation_verified": False,
        "production_authorized": False,
        "credentials_or_private_keys_accessed": False,
        "model_or_gpu_jobs_started": False,
    }


def observe(*, fetch=fetch_public, expected_source=SOURCE_MAIN_AT_REVIEW):
    if type(expected_source) is not str or _SHA40.fullmatch(expected_source) is None:
        raise PublicWitnessHold("EXPECTED_SOURCE_SHA_INVALID")
    observations = {}
    for method, path in ROUTES:
        observations[(method, path)] = fetch(method, path)
    report = check_observations(observations, expected_source=expected_source)
    report["observed_utc"] = datetime.now(UTC).isoformat()
    report["public_runtime_origin"] = CANONICAL_ORIGIN
    report["source_repository"] = SOURCE_REPOSITORY
    report["effect_budget"] = {
        "public_http_requests": len(ROUTES),
        "model_inference": 0,
        "paid_jobs": 0,
        "private_data_reads": 0,
        "provider_writes": 0,
    }
    return report


def save_create_only(path: Path, report: dict):
    raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    with path.open("xb") as out:
        out.write(raw)
    return hashlib.sha256(raw).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only public Hatun readiness witness. Always requires authenticated operator follow-up."
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-source", default=SOURCE_MAIN_AT_REVIEW)
    args = parser.parse_args(argv)
    try:
        report = observe(expected_source=args.expected_source)
        digest = save_create_only(args.out, report)
        print(
            json.dumps(
                {
                    "state": report["state"],
                    "reasons": report["reasons"],
                    "liveness_http": report["liveness_http"],
                    "readiness_http": report["readiness_http"],
                    "build_revision_matches_source": report["observed_build_sha"]
                    == args.expected_source,
                    "receipt_sha256": digest,
                    "production_authorized": False,
                },
                sort_keys=True,
            )
        )
    except (PublicWitnessHold, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "state": "HOLD",
                    "reason": str(exc)
                    if isinstance(exc, PublicWitnessHold)
                    else type(exc).__name__,
                    "production_authorized": False,
                },
                sort_keys=True,
            )
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
