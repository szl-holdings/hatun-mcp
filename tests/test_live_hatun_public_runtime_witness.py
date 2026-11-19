"""Hermetic source-owner tests; never make network requests or use credentials."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "live_hatun_public_runtime_witness.py"
SPEC = importlib.util.spec_from_file_location("hatun_public_runtime_witness", SOURCE)
assert SPEC is not None and SPEC.loader is not None
W = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(W)


def json_response(payload, status=200):
    return {
        "status": status,
        "content_type": "application/json; charset=utf-8",
        "raw": json.dumps(payload, sort_keys=True).encode("utf-8"),
    }


def good_observations():
    return {
        ("GET", "/healthz"): json_response(
            {
                "status": "ok",
                "service": "hatun-mcp",
                "chain_verified": True,
                "signer_mode": "ECDSA-P256",
            }
        ),
        ("GET", "/readyz"): json_response(
            {
                "status": "ready",
                "ready": True,
                "checks": {
                    "receipt_chain": "VERIFIED",
                    "signer": "CONFIGURED",
                    "authentication": "CONFIGURED",
                },
                "signer_mode": "ECDSA-P256",
            }
        ),
        ("GET", "/api/build-info"): json_response(
            {
                "service": "hatun-mcp",
                "build": {"revision": W.SOURCE_MAIN_AT_REVIEW},
            }
        ),
        ("HEAD", "/mcp/"): {
            "status": 401,
            "content_type": "",
            "raw": b"",
        },
    }


class PublicRuntimeWitnessTests(unittest.TestCase):
    def test_requested_model_auth_proof_never_faked(self):
        outcome = W.check_observations(
            good_observations(), expected_source=W.SOURCE_MAIN_AT_REVIEW
        )
        self.assertEqual(outcome["state"], "HOLD")
        self.assertTrue(outcome["release_readiness_self_reported"])
        self.assertTrue(outcome["anonymous_denial_observed"])
        self.assertFalse(outcome["operator_authenticated_tools_list_verified"])
        self.assertFalse(outcome["independent_dsse_signature_verified"])
        self.assertFalse(outcome["production_authorized"])

    def test_live_503_and_missing_auth_binding_hold(self):
        observations = good_observations()
        observations[("GET", "/readyz")] = json_response(
            {
                "status": "not_ready",
                "ready": False,
                "checks": {
                    "receipt_chain": "VERIFIED",
                    "signer": "CONFIGURED",
                    "authentication": "UNAVAILABLE",
                },
                "signer_mode": "ECDSA-P256",
            },
            status=503,
        )
        result = W.check_observations(
            observations, expected_source=W.SOURCE_MAIN_AT_REVIEW
        )
        self.assertIn("READYZ_NOT_ADMITTED", result["reasons"])
        self.assertIn("OPERATOR_AUTH_BINDING_UNAVAILABLE", result["reasons"])
        self.assertEqual(result["readiness_http"], 503)

    def test_source_revision_mismatch_held(self):
        data = good_observations()
        data[("GET", "/api/build-info")] = json_response(
            {"build": {"revision": "f" * 40}}
        )
        result = W.check_observations(data, expected_source=W.SOURCE_MAIN_AT_REVIEW)
        self.assertIn("DEPLOYED_SOURCE_REVISION_NOT_ADMITTED", result["reasons"])

    def test_health_200_does_not_make_ready(self):
        data = good_observations()
        data[("GET", "/readyz")] = json_response(
            {"status": "ready", "ready": True, "checks": {}}, status=503
        )
        result = W.check_observations(data, expected_source=W.SOURCE_MAIN_AT_REVIEW)
        self.assertTrue(result["liveness_observed"])
        self.assertFalse(result["release_readiness_self_reported"])
        self.assertEqual(result["state"], "HOLD")

    def test_mcp_402_payment_gate_is_not_operator_authentication(self):
        data = good_observations()
        data[("HEAD", "/mcp/")]["status"] = 402
        result = W.check_observations(data, expected_source=W.SOURCE_MAIN_AT_REVIEW)
        self.assertIn("MCP_PAYMENT_GATE_OBSERVED_NOT_OPERATOR_AUTH", result["reasons"])
        self.assertIn("MCP_UNAUTHENTICATED_DENIAL_NOT_PROVEN", result["reasons"])
        self.assertFalse(result["anonymous_denial_observed"])
        self.assertFalse(result["operator_authenticated_tools_list_verified"])
        self.assertFalse(result["production_authorized"])

    def test_no_mcp_anonymous_success(self):
        data = good_observations()
        data[("HEAD", "/mcp/")]["status"] = 200
        result = W.check_observations(data, expected_source=W.SOURCE_MAIN_AT_REVIEW)
        self.assertIn("MCP_ANONYMOUS_SURFACE_POSSIBLE", result["reasons"])
        self.assertFalse(result["anonymous_denial_observed"])

    def test_mcp_denial_is_not_operator_tool_proof(self):
        for code in (401, 403):
            with self.subTest(http=code):
                data = good_observations()
                data[("HEAD", "/mcp/")]["status"] = code
                result = W.check_observations(
                    data, expected_source=W.SOURCE_MAIN_AT_REVIEW
                )
                self.assertTrue(result["anonymous_denial_observed"])
                self.assertFalse(result["operator_authenticated_tools_list_verified"])

    def test_ready_boolean_impostor_not_accepted(self):
        data = good_observations()
        data[("GET", "/readyz")] = json_response(
            {
                "status": "ready",
                "ready": 1,
                "checks": {
                    "receipt_chain": "VERIFIED",
                    "signer": "CONFIGURED",
                    "authentication": "CONFIGURED",
                },
                "signer_mode": "ECDSA-P256",
            }
        )
        self.assertFalse(
            W.check_observations(data, expected_source=W.SOURCE_MAIN_AT_REVIEW)[
                "release_readiness_self_reported"
            ]
        )

    def test_missing_or_duplicate_json_keys_denied(self):
        for raw in (b"[]", b'{"ready":true,"ready":false}', b"{invalid"):
            with self.subTest(raw=raw), self.assertRaises(W.PublicWitnessHold):
                W.strict_json(raw)

    def test_nonfinite_json_denied(self):
        with self.assertRaises(W.PublicWitnessHold):
            W.strict_json(b'{"ready":NaN}')

    def test_response_byte_budget_denied(self):
        with self.assertRaisesRegex(W.PublicWitnessHold, "BYTE_BUDGET"):
            W.strict_json(b"a" * (W.MAX_BODY_BYTES + 1))

    def test_http_unsupported_methods_do_not_network(self):
        for method, path in (
            ("POST", "/mcp/"),
            ("GET", "/mcp/"),
            ("GET", "https://evil.invalid/readyz"),
            ("GET", "/pubkey"),
        ):
            with (
                self.subTest(method=method, path=path),
                self.assertRaisesRegex(W.PublicWitnessHold, "REQUEST_NOT_ALLOWLISTED"),
            ):
                W.fetch_public(method, path)

    def test_redirect_is_refused(self):
        self.assertIsNone(
            W.NoRedirect().redirect_request(
                None, None, 302, "redirect", {}, "https://evil.invalid"
            )
        )

    def test_invalid_source_sha_refused(self):
        with self.assertRaisesRegex(W.PublicWitnessHold, "EXPECTED_SOURCE_SHA_INVALID"):
            W.check_observations(good_observations(), expected_source="main")

    def test_malformed_observation_set_refused(self):
        with self.assertRaisesRegex(W.PublicWitnessHold, "OBSERVATION_SET_INVALID"):
            W.check_observations({}, expected_source=W.SOURCE_MAIN_AT_REVIEW)

    def test_mocked_single_bounded_pass(self):
        observed = good_observations()
        calls = []

        def fake_fetch(method, path):
            calls.append((method, path))
            return observed[(method, path)]

        report = W.observe(fetch=fake_fetch)
        self.assertEqual(calls, list(W.ROUTES))
        self.assertEqual(report["effect_budget"]["public_http_requests"], 4)
        self.assertEqual(report["effect_budget"]["model_inference"], 0)
        self.assertEqual(report["effect_budget"]["provider_writes"], 0)
        self.assertEqual(report["state"], "HOLD")

    def test_report_create_only_and_sha_stable(self):
        report = W.observe(fetch=lambda m, p: good_observations()[(m, p)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new-receipt.json"
            got = W.save_create_only(path, report)
            import hashlib

            self.assertEqual(got, hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                W.save_create_only(path, report)

    def test_http_500_not_green(self):
        data = good_observations()
        data[("GET", "/healthz")]["status"] = 500
        result = W.check_observations(data, expected_source=W.SOURCE_MAIN_AT_REVIEW)
        self.assertIn("HEALTHZ_UNAVAILABLE", result["reasons"])

    def test_unauthorized_source_short_prefix_not_admitted(self):
        data = good_observations()
        data[("GET", "/api/build-info")] = json_response(
            {"build": {"revision": W.SOURCE_MAIN_AT_REVIEW[:10]}}
        )
        result = W.check_observations(data, expected_source=W.SOURCE_MAIN_AT_REVIEW)
        self.assertIn("DEPLOYED_SOURCE_REVISION_NOT_ADMITTED", result["reasons"])


if __name__ == "__main__":
    unittest.main()
