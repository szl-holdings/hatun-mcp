"""Bounded, no-network, no-signer Hatun-MCP intent and stale-file falsifiers."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from hatun_mcp.deferred_intent_witness import (
    IntentError, snapshot_proposal, recheck_proposal,
)


class DeferredIntentWitnessTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        (self.root / "sample.txt").write_bytes(b"before")
        self.args = {"operation": "read_only", "limit": 5}

    def snapshot(self):
        return snapshot_proposal("example", self.args, self.root, ["sample.txt"])

    def test_clean_proposal_is_consistent_but_not_approved(self):
        w = self.snapshot()
        status = recheck_proposal(w, "example", self.args, self.root)
        self.assertEqual("UNCHANGED_UNAUTHORIZED", status["status"])
        self.assertEqual("NONE", status["tool_execution_authority"])
        self.assertFalse(w["approval_verified"])
        self.assertEqual(status, recheck_proposal(w, "example", self.args, self.root))

    def test_argument_mutation_after_snapshot_fails(self):
        w = self.snapshot()
        self.assertEqual("DENY", recheck_proposal(w, "example", {"operation": "write"}, self.root)["status"])
        self.assertEqual("ACTION_OR_ARGUMENTS_CHANGED", recheck_proposal(w, "other", self.args, self.root)["reason"])
        self.assertEqual("UNCHANGED_UNAUTHORIZED", recheck_proposal(w, "example", self.args, self.root)["status"])

    def test_inplace_modified_and_removed_file_denied(self):
        w = self.snapshot()
        (self.root / "sample.txt").write_bytes(b"after!")
        self.assertEqual("STALE_ARTIFACT", recheck_proposal(w, "example", self.args, self.root)["reason"])
        (self.root / "sample.txt").unlink()
        self.assertEqual("ARTIFACT_MISSING_OR_UNREADABLE", recheck_proposal(w, "example", self.args, self.root)["reason"])

    def test_snapshot_structural_tamper_denied(self):
        w = self.snapshot()
        w["artifacts"][0]["sha256"] = "b" * 64
        self.assertEqual("WITNESS_BYTES_CHANGED", recheck_proposal(w, "example", self.args, self.root)["reason"])

    def test_resealed_snapshot_never_becomes_approval(self):
        w = self.snapshot()
        # Even if an attacker can mint a new *internally consistent*
        # unkeyed witness, it still grants no permission.
        newer = snapshot_proposal("example", {"operation": "write"}, self.root, ["sample.txt"])
        self.assertEqual("UNCHANGED_UNAUTHORIZED", recheck_proposal(newer, "example", {"operation": "write"}, self.root)["status"])
        newer["approval_verified"] = True
        self.assertEqual("INVALID_AUTHORITY_CLAIM", recheck_proposal(newer, "example", {"operation": "write"}, self.root)["reason"])

    def test_noncanonical_or_oversized_args_denied(self):
        for bad in ({"limit": float("nan")}, {"unknown": object()}, {"text": "x" * 17000}):
            with self.subTest(value=list(bad)), self.assertRaises(IntentError):
                snapshot_proposal("example", bad, self.root, [])

    def test_path_traversal_and_symlink_denied(self):
        with self.assertRaisesRegex(IntentError, "INVALID_ARTIFACT_SELECTION"):
            snapshot_proposal("example", self.args, self.root, ["../private.txt"])
        (self.root / "link.txt").symlink_to(self.root / "sample.txt")
        with self.assertRaisesRegex(IntentError, "ARTIFACT_SYMLINK_NOT_ALLOWED"):
            snapshot_proposal("example", self.args, self.root, ["link.txt"])

    def test_workspace_disappearance_is_a_controlled_denial(self):
        w = self.snapshot()
        gone = self.root / "no_such_workspace"
        self.assertEqual("INVALID_WORKSPACE_ROOT", recheck_proposal(w, "example", self.args, gone)["reason"])
        with self.assertRaisesRegex(IntentError, "INVALID_WORKSPACE_ROOT"):
            snapshot_proposal("example", self.args, gone, [])

    def test_oversized_artifact_denied(self):
        (self.root / "sample.txt").write_bytes(b"x" * 131073)
        with self.assertRaisesRegex(IntentError, "ARTIFACT_TOO_LARGE"):
            self.snapshot()


if __name__ == "__main__":
    unittest.main()
