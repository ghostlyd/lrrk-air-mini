import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.audit import validate_replay  # noqa: E402
from lrrk_litewing_ai.adapters import JsonlTelemetryAdapter  # noqa: E402
from lrrk_litewing_ai.cli import main  # noqa: E402


FIXTURE = ROOT / "tests" / "fixtures" / "telemetry.jsonl"


class CliTests(unittest.TestCase):
    def test_offline_fixture_runs_without_credentials(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch("lrrk_litewing_ai.safety._now", return_value=datetime(2026, 9, 8, 12, tzinfo=timezone.utc)):
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

    def test_live_uavtalk_routes_exact_device_capture_and_duration(self):
        snapshot = next(JsonlTelemetryAdapter(FIXTURE).snapshots())
        adapter = patch("lrrk_litewing_ai.cli.UAVTalkAdapter", autospec=True)
        with tempfile.TemporaryDirectory() as directory, adapter as adapter_class:
            capture = Path(directory) / "private.uavtalk"
            adapter_class.return_value.snapshots.return_value = iter((snapshot,))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main([
                    "--input-format", "uavtalk-live",
                    "--device", "/dev/cu.wchusbserial410",
                    "--usb-location", "4-1",
                    "--private-capture", str(capture),
                    "--duration", "0.75",
                    "--json",
                ])

        self.assertEqual(result, 0)
        adapter_class.assert_called_once_with(
            device="/dev/cu.wchusbserial410",
            location="4-1",
            capture_path=capture,
            duration_s=0.75,
        )
        self.assertIn('"overall":', output.getvalue())

    def test_input_modes_reject_missing_and_cross_mode_flags(self):
        cases = (
            [],
            ["--input-format", "jsonl", "--device", "/dev/cu.test"],
            ["--input", str(FIXTURE), "--input-format", "uavtalk-live",
             "--device", "/dev/cu.test", "--usb-location", "4-1",
             "--private-capture", "/tmp/private.uavtalk"],
            ["--input-format", "uavtalk-live", "--device", "/dev/cu.test",
             "--usb-location", "4-1"],
            ["--input-format", "uavtalk-live", "--device", "/dev/cu.test",
             "--usb-location", "4-1", "--private-capture", "/tmp/private.uavtalk",
             "--duration", "nan"],
            ["--input-format", "uavtalk-live", "--device", "/dev/cu.test",
             "--usb-location", "4-1", "--private-capture", "/tmp/private.uavtalk",
             "--duration", "5.01"],
            ["--input", str(FIXTURE), "--input-format", "uavtalk",
             "--captured-at", "2026-09-09T10:00:00Z",
             "--private-capture", "/tmp/private.uavtalk"],
        )
        for argv in cases:
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(argv), 2)


if __name__ == "__main__":
    unittest.main()
