"""Host-only checks for the sanitized armed/nonzero-motor evidence record."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
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

    def test_exact_capture_firmware_source_and_probe_provenance_are_pinned(self):
        cases = []

        wrong_capture = copy.deepcopy(self.record)
        wrong_capture["capture"]["sha256"] = "0" * 64
        cases.append(("capture digest", wrong_capture))

        wrong_application = copy.deepcopy(self.record)
        wrong_application["provenance"]["installed_application_sha256"] = "0" * 64
        cases.append(("installed application digest", wrong_application))

        wrong_probe = copy.deepcopy(self.record)
        wrong_probe["provenance"]["probe_sha256"] = "0" * 64
        cases.append(("probe digest", wrong_probe))

        wrong_probe_test = copy.deepcopy(self.record)
        wrong_probe_test["provenance"]["probe_test_sha256"] = "0" * 64
        cases.append(("probe-test digest", wrong_probe_test))

        wrong_source = copy.deepcopy(self.record)
        wrong_source["provenance"]["flight_source_revision"] = "0" * 40
        cases.append(("flight source revision", wrong_source))

        for label, candidate in cases:
            with self.subTest(label=label), self.assertRaises(evidence.EvidenceError):
                evidence.validate_record(candidate)

    def test_exact_decoded_sample_set_and_counts_are_pinned(self):
        cases = []

        truncated_nonzero = copy.deepcopy(self.record)
        truncated_nonzero["decode"]["nonzero_actuator_samples"] = truncated_nonzero[
            "decode"
        ]["nonzero_actuator_samples"][:3]
        truncated_nonzero["decode"]["summary"].update({
            "nonzero_motor_samples": 3,
            "max_observed_motor_command": 80,
            "peak_motor_channels": [80, 0, 0, 70],
        })
        cases.append(("truncated nonzero sample set", truncated_nonzero))

        altered_motor = copy.deepcopy(self.record)
        altered_motor["decode"]["nonzero_actuator_samples"][0]["motors"][0] = 72
        cases.append(("altered in-range motor sample", altered_motor))

        altered_frame = copy.deepcopy(self.record)
        altered_frame["decode"]["nonzero_actuator_samples"][0]["valid_frame"] = 534
        cases.append(("altered valid-frame ordinal", altered_frame))

        truncated_zero = copy.deepcopy(self.record)
        zeros = truncated_zero["decode"]["post_nonzero_zero_samples"]
        truncated_zero["decode"]["post_nonzero_zero_samples"] = [
            zeros[0], zeros[1], zeros[-1]
        ]
        truncated_zero["decode"]["summary"]["post_nonzero_zero_samples"] = 3
        cases.append(("truncated trailing-zero sample set", truncated_zero))

        altered_count = copy.deepcopy(self.record)
        altered_count["decode"]["object_samples"]["FlightStatus"] = 33
        cases.append(("altered object sample count", altered_count))

        for label, candidate in cases:
            with self.subTest(label=label), self.assertRaises(evidence.EvidenceError):
                evidence.validate_record(candidate)

    def test_link_closure_residual_arming_hazard_is_explicit(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        report = (
            REPO_ROOT
            / "docs/verification/armed-nonzero-motor-proof-2026-09-09.md"
        ).read_text(encoding="utf-8")

        for text in (readme, report):
            normalized = " ".join(text.split())
            self.assertIn("serial link does not clear", normalized)
            self.assertIn("must assume `Always Armed` remains active", normalized)

    def test_limitations_cannot_be_replaced_with_passing_claims(self):
        candidate = copy.deepcopy(self.record)
        candidate["limitations"]["claims_not_established"] = [
            "flight readiness is established"
        ] * 4

        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(candidate)

    def test_cli_rejects_duplicate_json_object_names_before_hashing(self):
        original = EVIDENCE_PATH.read_text(encoding="utf-8")
        duplicate = (
            '  "limitations": {"terminal_scope": "ignored", '
            '"claims_not_established": ["flight readiness is established"]},\n'
            '  "limitations": {'
        )
        hostile = original.replace('  "limitations": {', duplicate, 1)
        self.assertNotEqual(hostile, original)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate-object.json"
            path.write_text(hostile, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = evidence.main([str(path)])

        self.assertEqual(rc, 2)

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
