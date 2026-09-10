"""Host-only checks for the sanitized armed/nonzero-motor evidence record."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import unittest
from pathlib import Path


PORT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PORT_ROOT.parents[1]
EVIDENCE_PATH = (
    REPO_ROOT
    / "docs/verification/evidence/armed-nonzero-motor-2026-09-09.json"
)
sys.path.insert(0, str(PORT_ROOT / "diagnostics"))

try:
    import arm_motor_evidence as evidence
except ModuleNotFoundError:
    evidence = None


class ArmMotorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(evidence, "arm/motor evidence verifier is not implemented")
        self.record = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    def test_committed_record_proves_bounded_nonzero_commands_while_armed(self):
        result = evidence.validate_record(self.record)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["nonzero_motor_samples"], 6)
        self.assertEqual(result["peak_motor_channels"], [128, 0, 0, 118])
        self.assertEqual(result["post_nonzero_zero_samples"], 11)
        self.assertEqual(result["terminal_state"], "ARMED_ZERO_RECEIVER_TIMED_OUT")

    def test_control_bounds_and_armed_state_are_fail_closed(self):
        cases = []

        excessive = copy.deepcopy(self.record)
        excessive["decode"]["nonzero_actuator_samples"][0]["motors"][0] = 201
        cases.append(("command above ceiling", excessive))

        disarmed = copy.deepcopy(self.record)
        disarmed["decode"]["nonzero_actuator_samples"][0]["flight_status"] = "Disarmed"
        cases.append(("nonzero sample while disarmed", disarmed))

        persistent = copy.deepcopy(self.record)
        persistent["transaction"]["persistent_write_sent"] = True
        cases.append(("persistent write", persistent))

        restored = copy.deepcopy(self.record)
        restored["transaction"]["restoration_skipped_by_request"] = False
        cases.append(("unrecorded restoration", restored))

        published = copy.deepcopy(self.record)
        published["capture"]["raw_capture_published"] = True
        cases.append(("raw capture publication", published))

        for label, candidate in cases:
            with self.subTest(label=label), self.assertRaises(evidence.EvidenceError):
                evidence.validate_record(candidate)

    def test_post_pulse_and_terminal_state_require_armed_zero_output(self):
        cases = []

        too_few_zero = copy.deepcopy(self.record)
        too_few_zero["decode"]["post_nonzero_zero_samples"] = too_few_zero[
            "decode"
        ]["post_nonzero_zero_samples"][:2]
        cases.append(("fewer than three zero samples", too_few_zero))

        terminal_nonzero = copy.deepcopy(self.record)
        terminal_nonzero["decode"]["terminal"]["motors"] = [1, 0, 0, 0]
        cases.append(("terminal motor command", terminal_nonzero))

        terminal_connected = copy.deepcopy(self.record)
        terminal_connected["decode"]["terminal"]["receiver_connected"] = True
        cases.append(("terminal receiver connected", terminal_connected))

        reordered = copy.deepcopy(self.record)
        reordered["decode"]["post_nonzero_zero_samples"][0]["valid_frame"] = 500
        cases.append(("zero evidence before nonzero evidence", reordered))

        for label, candidate in cases:
            with self.subTest(label=label), self.assertRaises(evidence.EvidenceError):
                evidence.validate_record(candidate)

    def test_cli_emits_machine_readable_pass(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = evidence.main([str(EVIDENCE_PATH)])

        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
