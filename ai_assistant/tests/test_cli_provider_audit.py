"""Real CLI/audit integration; only the external provider runner is replaced."""

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.audit import validate_replay
from lrrk_litewing_ai.cli import main


FIXTURE = ROOT / "tests" / "fixtures" / "telemetry.jsonl"
PROMPT = "private-prompt-7c91 café 🚁"
RESPONSE = "private-response-2a83 naïve 🛑"
EXCEPTION_SECRET = "private-exception-f19e sk-test-secret-only bearer synthetic-secret"


class CliProviderAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.audit_path = self.directory / "audit.jsonl"
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        # Two distinct observations catch accidentally binding to the first one.
        first = json.loads(FIXTURE.read_text(encoding="utf-8"))
        latest = dict(first, snapshot_id="fixture-latest", armed=True)
        self.input_path = self.directory / "telemetry.jsonl"
        self.input_path.write_text(
            json.dumps(first) + "\n" + json.dumps(latest) + "\n", encoding="utf-8"
        )

    def run_cli(self, *args, audit=True):
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ["--input", str(self.input_path)]
        if audit:
            argv += ["--audit-log", str(self.audit_path)]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(argv + list(args))
        return status, stdout.getvalue(), stderr.getvalue()

    def assert_request(self, records):
        self.assertEqual([record["event_type"] for record in records[-5:]], [
            "snapshot_received", "preflight_result",
            "snapshot_received", "preflight_result", "provider_request",
        ])
        snapshot_hash = records[-3]["payload"]["snapshot_hash"]
        self.assertNotEqual(snapshot_hash, records[-5]["payload"]["snapshot_hash"])
        self.assertEqual(records[-1]["payload"], {
            "mode": "openai",
            "snapshot_hash": snapshot_hash,
            "prompt_bytes": len(PROMPT.encode("utf-8")),
            "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        })
        return snapshot_hash

    def assert_private_chain(self):
        records = validate_replay(self.audit_path)
        raw = self.audit_path.read_text(encoding="utf-8")
        for secret in (PROMPT, RESPONSE, EXCEPTION_SECRET, "private-prompt-7c91",
                       "private-response-2a83", "private-exception-f19e"):
            self.assertNotIn(secret, raw)
        for record in records:
            if record["event_type"].startswith("provider_"):
                self.assertEqual(record["source"], {})
        return records

    def test_success_is_chained_before_and_after_runner_and_preserves_stdout(self):
        for output_flags in ((), ("--json",)):
            with self.subTest(output_flags=output_flags):
                def runner(runtime, prompt):
                    # A replay here proves the request is on disk before execution.
                    snapshot_hash = self.assert_request(validate_replay(self.audit_path))
                    self.assertEqual(runtime.latest.snapshot_hash(), snapshot_hash)
                    self.assertEqual(prompt, PROMPT)
                    return RESPONSE

                with patch("lrrk_litewing_ai.cli._live_prompt", new=runner):
                    status, stdout, stderr = self.run_cli(
                        "--live-agent", "--prompt", PROMPT, *output_flags
                    )
                self.assertEqual(status, 0)
                self.assertEqual(stderr, "")
                if output_flags:
                    self.assertEqual(json.loads(stdout.splitlines()[-1]), {"assistant": RESPONSE})
                else:
                    self.assertEqual(stdout.splitlines()[-1], "assistant: " + RESPONSE)
                records = self.assert_private_chain()
                snapshot_hash = self.assert_request(records[:-1])
                self.assertEqual(records[-1]["event_type"], "provider_result")
                self.assertEqual(records[-1]["payload"], {
                    "outcome": "completed", "snapshot_hash": snapshot_hash,
                    "response_bytes": len(RESPONSE.encode("utf-8")),
                    "response_sha256": hashlib.sha256(RESPONSE.encode("utf-8")).hexdigest(),
                })
                self.assertEqual(len(records), 6 if not output_flags else 12)

    def test_failure_records_only_exception_class_and_never_discloses_message(self):
        def runner(runtime, prompt):
            self.assert_request(validate_replay(self.audit_path))
            raise RuntimeError(EXCEPTION_SECRET + PROMPT + RESPONSE)

        with patch("lrrk_litewing_ai.cli._live_prompt", new=runner):
            status, stdout, stderr = self.run_cli("--live-agent", "--prompt", PROMPT)
        self.assertEqual(status, 3)
        self.assertEqual(stderr, "assistant request blocked\n")
        for secret in (PROMPT, RESPONSE, EXCEPTION_SECRET):
            self.assertNotIn(secret, stdout + stderr)
        records = self.assert_private_chain()
        snapshot_hash = self.assert_request(records[:-1])
        self.assertEqual(len(records), 6)
        self.assertEqual(records[-1]["event_type"], "provider_result")
        self.assertEqual(records[-1]["payload"], {
            "outcome": "blocked", "snapshot_hash": snapshot_hash,
            "error_class": "RuntimeError",
        })

    def test_missing_key_attempt_is_audited_without_importing_sdk(self):
        status, _, stderr = self.run_cli("--live-agent", "--prompt", PROMPT)
        self.assertEqual(status, 3)
        records = self.assert_private_chain()
        snapshot_hash = self.assert_request(records[:-1])
        self.assertEqual(stderr, "assistant request blocked\n")
        self.assertEqual(records[-1]["event_type"], "provider_result")
        self.assertEqual(records[-1]["payload"], {
            "outcome": "blocked", "snapshot_hash": snapshot_hash,
            "error_class": "LiveProviderUnavailable",
        })

    def test_offline_and_no_prompt_validation_do_not_append_provider_events(self):
        for args, expected_status in (((), 0), (("--prompt", PROMPT), 0),
                                      (("--live-agent",), 3)):
            with self.subTest(args=args):
                def forbidden_runner(runtime, prompt):
                    self.fail("provider runner must not execute")

                with patch("lrrk_litewing_ai.cli._live_prompt", new=forbidden_runner):
                    status, _, stderr = self.run_cli(*args)
                self.assertEqual(status, expected_status)
                if expected_status == 3:
                    self.assertEqual(stderr, "live-agent mode blocked\n")
                self.assertTrue(all(record["event_type"] in {
                    "snapshot_received", "preflight_result"
                } for record in self.assert_private_chain()))

    def test_no_audit_log_preserves_success_and_creates_no_audit_file(self):
        with patch("lrrk_litewing_ai.cli._live_prompt", return_value=RESPONSE):
            status, stdout, stderr = self.run_cli("--live-agent", "--prompt", PROMPT, audit=False)
        self.assertEqual(status, 0)
        self.assertEqual(stdout.splitlines()[-1], "assistant: " + RESPONSE)
        self.assertEqual(stderr, "")
        self.assertEqual(list(self.directory.iterdir()), [self.input_path])

    def test_no_audit_log_still_sanitizes_provider_failure(self):
        with patch("lrrk_litewing_ai.cli._live_prompt", side_effect=RuntimeError(EXCEPTION_SECRET)):
            status, stdout, stderr = self.run_cli("--live-agent", "--prompt", PROMPT, audit=False)
        self.assertEqual(status, 3)
        self.assertEqual(stderr, "assistant request blocked\n")
        self.assertNotIn(EXCEPTION_SECRET, stdout + stderr)
        self.assertEqual(list(self.directory.iterdir()), [self.input_path])


if __name__ == "__main__":
    unittest.main()
