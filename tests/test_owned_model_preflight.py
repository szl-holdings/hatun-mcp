"""Hermetic tests for the read-only owned-model preflight."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "owned_model_preflight.py"
spec = importlib.util.spec_from_file_location("owned_model_preflight", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Response:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, *_):
        return json.dumps(self.value).encode("utf-8")

class TestPreflight(unittest.TestCase):
    def test_unknown_model_denied_without_network(self):
        with patch.object(module.urllib.request, "urlopen") as open_url:
            with self.assertRaises(ValueError):
                module.inspect("attacker/unknown")
            open_url.assert_not_called()

    def test_matching_identity_and_sha_metadata_only(self):
        model = module.MODEL_IDS[0]
        with patch.object(module.urllib.request, "urlopen", return_value=Response({"id": model, "sha": "a" * 40, "private": False})):
            result = module.inspect(model)
        self.assertEqual(result["status"], "METADATA_ONLY")
        self.assertEqual(result["reason"], "not_inference_proof")

    def test_identity_mismatch_is_unknown(self):
        with patch.object(module.urllib.request, "urlopen", return_value=Response({"id": "other/model", "sha": "a" * 40})):
            result = module.inspect(module.MODEL_IDS[0])
        self.assertEqual(result["status"], "UNKNOWN")

    def test_http_error_does_not_include_provider_body(self):
        with patch.object(module.urllib.request, "urlopen", side_effect=HTTPError("https://huggingface.co", 401, "denied", {}, io.BytesIO(b"SECRET"))):
            result = module.inspect(module.MODEL_IDS[0], token="SECRET")
        self.assertEqual(result["http_status"], 401)
        self.assertNotIn("SECRET", json.dumps(result))

    def test_cli_never_claims_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "report.json")
            with patch.object(module, "inspect", side_effect=lambda m, **kwargs: {"id": m, "status": "METADATA_ONLY"}):
                self.assertEqual(module.main(["--output", out]), 0)
            report = json.loads(Path(out).read_text())
            self.assertFalse(report["inference_verified"])
            self.assertFalse(report["production_qualified"])
            self.assertEqual(len(report["models"]), len(module.MODEL_IDS))

    def test_incomplete_inventory_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(module, "inspect", side_effect=lambda m, **kwargs: {"id": m, "status": "UNKNOWN"}):
                self.assertEqual(module.main(["--output", str(Path(tmp) / "report.json")]), 2)

if __name__ == "__main__":
    unittest.main()
