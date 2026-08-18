import json
import tempfile
import unittest
from pathlib import Path

from scripts.sanitize_pipeline_result import sanitize


class SanitizePipelineResultTests(unittest.TestCase):
    def test_removes_secrets_and_raw_payloads_recursively(self):
        value = sanitize({
            "quality_status": "SUCCESS",
            "evidence": ["verified"],
            "api_key": "must-not-persist",
            "nested": {"authorization": "Bearer secret", "raw_jd": "private text", "safe": "ok"},
        })
        self.assertEqual(value["quality_status"], "SUCCESS")
        self.assertEqual(value["evidence"], ["verified"])
        self.assertNotIn("api_key", value)
        self.assertNotIn("authorization", value["nested"])
        self.assertNotIn("raw_jd", value["nested"])
        self.assertEqual(value["nested"]["safe"], "ok")

    def test_bounds_large_values(self):
        value = sanitize({"evidence": ["x" * 10000] * 200})
        self.assertLessEqual(len(value["evidence"]), 100)
        self.assertLessEqual(len(value["evidence"][0]), 8015)

    def test_cli_writes_protocol_and_failure_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "missing.json"
            target = Path(directory) / "pipeline-result.json"
            from scripts.sanitize_pipeline_result import main
            import sys
            old_argv = sys.argv
            try:
                sys.argv = ["sanitize_pipeline_result.py", str(source), str(target)]
                self.assertEqual(main(), 0)
            finally:
                sys.argv = old_argv
            output = json.loads(target.read_text())
            self.assertEqual(output["artifact_protocol"], "career-os-pipeline-result-v1")
            self.assertEqual(output["quality_status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
