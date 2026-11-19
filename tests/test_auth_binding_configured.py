"""Plain-mapping regression tests for Hatun operator-binding readiness.

These tests never create credentials, change os.environ, or admit a transport.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hatun_mcp.server_http import http_auth_configured


PREFIX = "HATUN_MCP_SCOPE_"
CANONICAL_NAME = PREFIX + "a" * 16


class AuthConfiguredMappingTests(unittest.TestCase):
    def test_canonical_lowercase_fingerprint_all_valid_scopes(self):
        for fingerprint in ("0" * 16, "0123456789abcdef", "f" * 16):
            for scope in ("read", "write", "admin"):
                with self.subTest(fingerprint=fingerprint, scope=scope):
                    self.assertTrue(
                        http_auth_configured({PREFIX + fingerprint: scope})
                    )

    def test_noncanonical_fingerprint_only_does_not_admit_plain_mapping(self):
        for fingerprint in ("ABCDEF0123456789", "A" * 16, "aBcDeF0123456789"):
            with self.subTest(fingerprint=fingerprint):
                self.assertFalse(
                    http_auth_configured({PREFIX + fingerprint: "read"})
                )

    def test_noncanonical_prefix_only_does_not_admit_plain_mapping(self):
        for prefix in (PREFIX.lower(), "Hatun_Mcp_Scope_"):
            with self.subTest(prefix=prefix):
                self.assertFalse(
                    http_auth_configured({prefix + "a" * 16: "read"})
                )

    def test_malformed_or_unknown_bindings_fail_closed(self):
        cases = [
            {},
            {CANONICAL_NAME: ""},
            {CANONICAL_NAME: "owner"},
            {CANONICAL_NAME: "READ"},
            {CANONICAL_NAME: " read"},
            {CANONICAL_NAME: "read "},
            {CANONICAL_NAME: None},
            {PREFIX + "a" * 15: "read"},
            {PREFIX + "a" * 17: "read"},
            {PREFIX + "g" * 16: "read"},
            {PREFIX + "a" * 16 + "_EXTRA": "read"},
            {"OTHER_" + "a" * 16: "read"},
            {None: "read"},
            {123: "read"},
        ]
        for mapping in cases:
            with self.subTest(mapping=mapping):
                self.assertFalse(http_auth_configured(mapping))

    def test_noncanonical_alias_cannot_override_canonical_value(self):
        uppercase_alias = PREFIX + "A" * 16
        self.assertFalse(
            http_auth_configured({uppercase_alias: "admin", CANONICAL_NAME: "unknown"})
        )
        self.assertFalse(
            http_auth_configured({uppercase_alias: "admin", CANONICAL_NAME: ""})
        )
        self.assertTrue(
            http_auth_configured({uppercase_alias: "unknown", CANONICAL_NAME: "read"})
        )

    def test_unrelated_entries_do_not_hide_exact_valid_binding(self):
        mapping = {
            "OTHER_" + "a" * 16: "read",
            PREFIX + "A" * 16: "admin",
            PREFIX + "0" * 16: "write",
        }
        self.assertTrue(http_auth_configured(mapping))


if __name__ == "__main__":
    unittest.main()
