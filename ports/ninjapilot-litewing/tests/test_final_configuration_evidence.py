"""Fail-closed checks for the final LiteWing flight-configuration record."""

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
    / "docs/verification/evidence/final-flight-configuration-2026-09-10.json"
)
sys.path.insert(0, str(PORT_ROOT / "diagnostics"))

try:
    import final_configuration_evidence as evidence
except ModuleNotFoundError:
    evidence = None


class FinalConfigurationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            evidence, "final-configuration evidence verifier is not implemented"
        )
        self.record = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    def test_committed_record_clears_the_four_named_configuration_gates(self):
        result = evidence.validate_record(self.record)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["arming_policy"], "Yaw Right")
        self.assertEqual(result["peak_motor_channels"], [59, 0, 0, 62])
        self.assertEqual(result["motor_directions"], 4)
        self.assertEqual(result["terminal_state"], "DISARMED_ZERO")

    def test_normal_arming_and_terminal_zero_requirements_fail_closed(self):
        cases = []

        always_armed = copy.deepcopy(self.record)
        always_armed["arming_configuration"]["policy"] = "Always Armed"
        cases.append(("always armed policy", always_armed))

        not_persisted = copy.deepcopy(self.record)
        not_persisted["arming_configuration"]["post_reset_readback_confirmed"] = False
        cases.append(("unverified persistence", not_persisted))

        did_not_arm = copy.deepcopy(self.record)
        did_not_arm["normal_arming_proof"]["reached_armed"] = False
        cases.append(("did not arm", did_not_arm))

        excessive = copy.deepcopy(self.record)
        excessive["normal_arming_proof"]["peak_motor_channels"][0] = 201
        cases.append(("command above ceiling", excessive))

        terminal_nonzero = copy.deepcopy(self.record)
        terminal_nonzero["final_idle"]["motor_channels"] = [1, 0, 0, 0]
        cases.append(("terminal nonzero", terminal_nonzero))

        for label, candidate in cases:
            with self.subTest(label=label), self.assertRaises(evidence.EvidenceError):
                evidence.validate_record(candidate)

    def test_motor_direction_and_imu_orientation_are_complete_but_bounded(self):
        wrong_direction = copy.deepcopy(self.record)
        wrong_direction["motor_mapping"][0]["observed_rotation"] = "CW"
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(wrong_direction)

        synchronized = copy.deepcopy(self.record)
        synchronized["motor_video"]["synchronized_with_uart_capture"] = True
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(synchronized)

        six_face_claim = copy.deepcopy(self.record)
        six_face_claim["imu"]["six_face_accelerometer_calibration_performed"] = True
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(six_face_claim)

        bad_gravity = copy.deepcopy(self.record)
        bad_gravity["imu"]["stationary_accel_mean_mps2"][2] = 9.43
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(bad_gravity)

    def test_exact_source_capture_video_and_derived_imu_values_are_pinned(self):
        cases = []

        wrong_source = copy.deepcopy(self.record)
        wrong_source["source"]["wrapper_commit"] = "0" * 40
        cases.append(("wrapper source", wrong_source))

        wrong_capture = copy.deepcopy(self.record)
        wrong_capture["evidence_handling"]["capture_records"][0]["sha256"] = "0" * 64
        cases.append(("capture digest", wrong_capture))

        wrong_video_direction = copy.deepcopy(self.record)
        wrong_video_direction["motor_video"]["direction_observations"][0][
            "rotation"
        ] = "CW"
        cases.append(("video direction", wrong_video_direction))

        wrong_gravity_norm = copy.deepcopy(self.record)
        wrong_gravity_norm["imu"]["gravity_norm_mps2"] = 9.8
        cases.append(("derived gravity norm", wrong_gravity_norm))

        nonstationary_gyro = copy.deepcopy(self.record)
        nonstationary_gyro["imu"]["stationary_gyro_mean_dps"] = [200.0] * 3
        cases.append(("nonstationary gyro", nonstationary_gyro))

        missing_deviation = copy.deepcopy(self.record)
        missing_deviation["imu"].pop("stationary_gyro_pstdev_dps")
        cases.append(("missing stationary deviation", missing_deviation))

        wrong_video_measurement = copy.deepcopy(self.record)
        wrong_video_measurement["motor_video"]["direction_observations"][0][
            "axis_angles_deg_mod_180"
        ] = [10, 20, 30, 40, 50, 60]
        cases.append(("video angle sequence", wrong_video_measurement))

        fabricated_attitude = copy.deepcopy(self.record)
        fabricated_attitude["imu"].update({
            "gravity_inferred_roll_deg": 45.0,
            "attitude_roll_deg": 45.0,
        })
        cases.append(("fabricated matching attitude", fabricated_attitude))

        no_normal_input = copy.deepcopy(self.record)
        no_normal_input["normal_arming_proof"].update({
            "connected_low_samples_before_arm": 0,
            "connected_arming_samples": 0,
        })
        cases.append(("missing normal arming input", no_normal_input))

        altered_peaks = copy.deepcopy(self.record)
        altered_peaks["normal_arming_proof"]["peak_motor_channels"] = [199] * 4
        cases.append(("altered motor peaks", altered_peaks))

        wrong_image_size = copy.deepcopy(self.record)
        wrong_image_size["source"]["application_bytes"] += 1
        cases.append(("application size", wrong_image_size))

        wrong_timeout = copy.deepcopy(self.record)
        wrong_timeout["arming_configuration"]["armed_timeout_ms"] = 1000
        cases.append(("armed timeout", wrong_timeout))

        wrong_imu_counts = copy.deepcopy(self.record)
        wrong_imu_counts["imu"].update({"accel_samples": 99, "gyro_samples": 99})
        cases.append(("IMU sample counts", wrong_imu_counts))

        altered_live_attitude = copy.deepcopy(self.record)
        altered_live_attitude["imu"]["attitude_roll_deg"] += 0.5
        cases.append(("live attitude", altered_live_attitude))

        wrong_video_duration = copy.deepcopy(self.record)
        wrong_video_duration["motor_video"]["duration_seconds"] = 13.0
        cases.append(("video duration", wrong_video_duration))

        for label, candidate in cases:
            with self.subTest(label=label), self.assertRaises(evidence.EvidenceError):
                evidence.validate_record(candidate)

    def test_private_raw_evidence_and_remaining_flight_boundary_are_enforced(self):
        published = copy.deepcopy(self.record)
        published["evidence_handling"]["raw_captures_published"] = True
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(published)

        no_battery_boundary = copy.deepcopy(self.record)
        no_battery_boundary["not_established"] = [
            item
            for item in no_battery_boundary["not_established"]
            if "battery" not in item.casefold()
        ]
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(no_battery_boundary)

        extra_private_capture = copy.deepcopy(self.record)
        extra_private_capture["evidence_handling"]["raw_uart_capture_base64"] = (
            "ZHVtbXktcHJpdmF0ZS1ieXRlcw=="
        )
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(extra_private_capture)

        published_identifier = copy.deepcopy(self.record)
        published_identifier["source"]["hardware_serial"] = "private-identifier"
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(published_identifier)

        contradictory_text = copy.deepcopy(self.record)
        contradictory_text["startup"]["advisory_explanation"] = (
            "Critical alarms were present."
        )
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(contradictory_text)

        invented_flight_gate = copy.deepcopy(self.record)
        invented_flight_gate["flight_readiness"] = "PASS_FOR_FREE_FLIGHT"
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_record(invented_flight_gate)

    def test_cli_rejects_duplicate_json_names_and_emits_machine_readable_pass(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = evidence.main([str(EVIDENCE_PATH)])

        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "PASS")

        original = EVIDENCE_PATH.read_text(encoding="utf-8")
        hostile = original.replace(
            '  "not_established": [',
            '  "not_established": ["flight is established"],\n'
            '  "not_established": [',
            1,
        )
        self.assertNotEqual(hostile, original)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text(hostile, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = evidence.main([str(path)])

        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
