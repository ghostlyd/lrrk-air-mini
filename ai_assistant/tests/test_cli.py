import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.audit import validate_replay  # noqa: E402
from lrrk_litewing_ai.cli import main  # noqa: E402


FIXTURE = ROOT / "tests" / "fixtures" / "telemetry.jsonl"


class CliTests(unittest.TestCase):
    def test_offline_fixture_runs_without_credentials(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(["--input", str(FIXTURE), "--json", "--prompt", "run preflight"])
        self.assertEqual(result, 0)
        self.assertIn('"overall": "PASS"', output.getvalue())

    def test_audit_log_is_replayable(self):
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            result = main(["--input", str(FIXTURE), "--audit-log", str(audit_path)])
            self.assertEqual(result, 0)
            self.assertEqual(len(validate_replay(audit_path)), 2)

    def test_malformed_input_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text("not-json\n", encoding="utf-8")
            result = main(["--input", str(path)])
            self.assertEqual(result, 2)

    def test_live_mode_refuses_missing_key(self):
        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            result = main(["--input", str(FIXTURE), "--live-agent"])
        finally:
            if original is not None:
                os.environ["OPENAI_API_KEY"] = original
        self.assertEqual(result, 3)


if __name__ == "__main__":
    unittest.main()
