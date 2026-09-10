#!/usr/bin/env python3
"""Validate the sanitized final LiteWing configuration evidence record."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path


class EvidenceError(ValueError):
    """Raised when a record does not satisfy the committed evidence contract."""


HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_MAPPING = [
    (1, 5, "front-right", "B", "black/white", "CCW", -127),
    (2, 6, "rear-right", "A", "red/blue", "CW", 127),
    (3, 3, "rear-left", "B", "black/white", "CCW", -127),
    (4, 4, "front-left", "A", "red/blue", "CW", 127),
]
EXPECTED_SOURCE = {
    "wrapper_commit": "37f2476c6984f15dfe2b9ecd2861321652497804",
    "ninjapilot_commit": "ac77304a58de6c8bd552f94668b46903adb71cb2",
    "main_merge_commit": "dc3345dab633557de72e901627e31b7ffaea78b0",
}
EXPECTED_APPLICATION_SHA256 = (
    "98214708fcf511b3ccfb3a5511784791dda4166d87cd809102393e395d37f013"
)
EXPECTED_RECORD_SHA256 = (
    "e89ae4f8b93f2af6eeb0eaa22dc8ea064499b897ab3fc4d81793187b7c82d4ca"
)
EXPECTED_CAPTURES = [
    (
        "merged-image identity and settled startup",
        43704,
        "eaee4ab6e69b304ccba25e4f9cadd1747e545e98679012336bca772bd77631c6",
        "4bf16358b8826c18603bad3661bd715e0af71ea8a48159ae970a09102e438fd6",
    ),
    (
        "persist normal Yaw Right arming policy",
        29374,
        "84b4d73c12d3db1a83c2325222fa9ef6130275efa3ec9595bbe25d8457eb2b0c",
        "84af12b3bb87fc542e636b6775cd1d699003840532ef6c25283b229957ad8466",
    ),
    (
        "post-reset policy and boot verification",
        43546,
        "e0da41417d7c6399016e142cee1088a7cd6cf3b466ecf462d2441906fe23afd7",
        "d20c8e250126608aecfce304a6ec4d8fd4cf414112fdb33dee62e32ceade805a",
    ),
    (
        "normal arming and bounded motor command",
        47198,
        "369484118eba2569f7aea04ed3e2f6535a0b2f4fdd15fe3a535b441aae14e885",
        "40bafd1b27252208627b08de09b894b3f04fb64d69da2f9a4bd72279d88e57d0",
    ),
    (
        "closing reset-neutral idle state",
        81566,
        "586da78dbd3a9aa2983b8d3821544f25d60b49b499a825557adeb4c6f885ea12",
        "053111d231e912d9516ef51b0c7a91fb328cd691056b844fcfea95a2b3cb994c",
    ),
]
EXPECTED_LIMITATIONS = [
    "battery-powered operation or battery, charger, and connector validation",
    "six-face accelerometer precision calibration",
    "propeller selection, fitting, balance, and clearance",
    "airworthiness, controlled hover, or free flight",
]
EXPECTED_VIDEO_OBSERVATIONS = [
    (1, "front-right", (6.533, 6.700),
     (14.3, 144.3, 102.8, 77.3, 66.9, 62.3), "CCW"),
    (2, "rear-right", (12.067, 12.200),
     (48.4, 58.8, 79.6, 87.3, 94.7), "CW"),
    (3, "rear-left", (0.633, 0.733),
     (165.3, 142.0, 124.6, 116.9), "CCW"),
    (4, "front-left", (3.533, 3.833),
     (70.4, 140.3, 9.5, 71.5, 125.5, 158.0, 3.1, 23.6, 37.6, 43.9), "CW"),
]
EXPECTED_ACCEL_MEAN = [0.0183555465, 0.6545481450, -9.4300288094]
EXPECTED_ACCEL_PSTDEV = [0.0217976110, 0.0151714479, 0.0272306269]
EXPECTED_GYRO_MEAN = [0.0152227926, -0.0103093602, 0.0313501507]
EXPECTED_GYRO_PSTDEV = [0.0740044687, 0.0572655884, 0.0725200956]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _require_digest(value: object, label: str) -> None:
    _require(isinstance(value, str) and HEX_64.fullmatch(value) is not None,
             f"{label} is not a SHA-256 digest")


def _reject_duplicate_names(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON object name: {key}")
        result[key] = value
    return result


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream, object_pairs_hook=_reject_duplicate_names)
    _require(isinstance(value, dict), "top-level JSON value must be an object")
    return value


def validate_record(record: dict) -> dict:
    _require(record.get("schema") == "lrrk.litewing.final-flight-configuration.v1",
             "unsupported final-configuration evidence schema")
    record_bytes = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    _require(hashlib.sha256(record_bytes).hexdigest() == EXPECTED_RECORD_SHA256,
             "sanitized record differs from the reviewed evidence payload")
    _require(record.get("evidence_id") ==
             "litewing-final-flight-configuration-2026-09-10",
             "unexpected final-configuration evidence id")

    source = record["source"]
    for key in ("wrapper_commit", "ninjapilot_commit", "main_merge_commit"):
        _require(isinstance(source[key], str) and HEX_40.fullmatch(source[key]),
                 f"source.{key} is not a full Git commit")
        _require(source[key] == EXPECTED_SOURCE[key], f"source.{key} changed")
    _require(source["wrapper_commit_in_main_history"] is True,
             "installed wrapper source is not recorded in main history")
    _require(source["firmware_marker"] == "LRRK37f2476c6984f15d",
             "unexpected firmware marker")
    _require(source["application_bytes"] == 359776,
             "installed application byte count changed")
    _require_digest(source["application_built_sha256"], "built application")
    _require(source["application_built_sha256"] == EXPECTED_APPLICATION_SHA256,
             "unexpected installed application digest")
    _require(source["application_built_sha256"] == source["application_readback_sha256"],
             "application readback does not equal the built image")

    expected_gates = {
        "current_image_identity": "PASS",
        "startup_alarms": "PASS",
        "motor_corner_direction_mapping": "PASS",
        "imu_orientation_calibration": "PASS_FOR_INITIAL_ATTITUDE_RATE_FLIGHT",
    }
    _require(record["gates"] == expected_gates,
             "the four named configuration gates are not all at their bounded pass state")

    handling = record["evidence_handling"]
    _require(handling["raw_captures_published"] is False,
             "private raw captures must not be published")
    _require(handling["hardware_serial_or_mac_published"] is False,
             "hardware serial or MAC must not be published")
    actual_captures = []
    for index, capture in enumerate(handling["capture_records"]):
        _require(isinstance(capture["bytes"], int) and capture["bytes"] > 0,
                 f"capture {index} has no byte count")
        _require_digest(capture["sha256"], f"capture {index}")
        _require_digest(capture["report_sha256"], f"capture report {index}")
        actual_captures.append((
            capture["purpose"], capture["bytes"], capture["sha256"],
            capture["report_sha256"],
        ))
    _require(actual_captures == EXPECTED_CAPTURES, "capture provenance changed")

    physical = record["physical_conditions"]
    _require(physical == {
        "propellers_removed": True,
        "contained": True,
        "battery_connected": False,
        "power_source": "USB-C",
    }, "bench physical conditions are not the reviewed prop-off USB condition")

    startup = record["startup"]
    _require(startup["boot_fault"] == "OK", "BootFault is not clear")
    _require(startup["critical_or_error_alarms"] == [],
             "startup contains a Critical or Error alarm")
    _require(startup["active_advisory_alarms"] == ["Receiver:Warning"],
             "unexpected active startup advisory alarms")
    _require(startup["unused_optional_sensors_uninitialised"] is True,
             "unused optional sensor alarm boundary is not explicit")

    arming = record["arming_configuration"]
    _require(arming["policy"] == "Yaw Right", "arming policy is not normal Yaw Right")
    _require(arming["persistence_operation"] == "Completed",
             "arming-policy persistence did not complete")
    _require(arming["post_reset_readback_confirmed"] is True,
             "arming policy was not verified after reset")
    _require(arming["armed_timeout_ms"] == 30000,
             "configured ArmedTimeout changed")
    _require(arming["pre_write_flight_status"] == "Disarmed" and
             arming["pre_write_motor_channels"] == [0, 0, 0, 0],
             "arming-policy write did not begin disarmed at zero output")

    proof = record["normal_arming_proof"]
    _require(proof["policy"] == "Yaw Right", "arming proof used a different policy")
    _require(proof["persistent_write_sent"] is False,
             "normal arming proof unexpectedly wrote persistent settings")
    _require(proof["reached_armed"] is True, "normal arming proof never reached Armed")
    _require(proof["connected_low_samples_before_arm"] == 3 and
             proof["connected_arming_samples"] == 21,
             "normal arming input observations changed")
    _require(proof["nonzero_motor_samples"] == 4,
             "nonzero motor sample count changed")
    _require(proof["command_scale"] == [0, 1000] and proof["command_ceiling"] == 200,
             "motor command scale or evidence ceiling changed")
    peaks = proof["peak_motor_channels"]
    _require(len(peaks) == 4 and any(value > 0 for value in peaks) and
             all(isinstance(value, int) and 0 <= value <= proof["command_ceiling"]
                 for value in peaks),
             "peak motor channels violate the bounded proof")
    _require(peaks == [59, 0, 0, 62], "observed peak motor channels changed")
    _require(proof["zero_samples_after_nonzero"] == 12,
             "return-to-zero observation count changed")
    proof_terminal = proof["terminal"]
    _require(proof_terminal == {
        "flight_status": "Armed",
        "motor_channels": [0, 0, 0, 0],
        "receiver_connected": False,
    }, "arming transaction did not terminate Armed at zero with receiver disconnected")

    final_idle = record["final_idle"]
    _require(final_idle["reset_neutral_open"] is True,
             "final idle observation was not reset neutral")
    _require(final_idle["request_only"] is True,
             "final idle observation was not request-only")
    _require(final_idle["arming_policy"] == "Yaw Right",
             "final idle policy does not match persisted Yaw Right")
    _require(final_idle["flight_time_ms"] == 854743,
             "final idle flight time changed")
    _require(final_idle["automatic_disarm_interpretation"] ==
             "consistent with configured timeout; not a continuous trace",
             "automatic-disarm evidence boundary changed")
    _require(final_idle["flight_status"] == "Disarmed" and
             final_idle["motor_channels"] == [0, 0, 0, 0],
             "final idle state is not Disarmed with zero motor commands")
    _require(final_idle["critical_or_error_alarms"] == [],
             "final idle contains a Critical or Error alarm")
    _require(final_idle["boot_fault"] == "OK", "final idle BootFault is not clear")
    _require(final_idle["unused_optional_sensors_uninitialised"] is True,
             "final idle optional-sensor boundary is not explicit")

    mapping = record["motor_mapping"]
    _require(len(mapping) == 4, "motor mapping does not contain four channels")
    actual_mapping = [
        (
            item["channel"], item["gpio"], item["corner"], item["motor_class"],
            item["wires"], item["observed_rotation"], item["mixer_yaw"],
        )
        for item in mapping
    ]
    _require(actual_mapping == EXPECTED_MAPPING, "motor mapping or direction changed")

    video = record["motor_video"]
    _require(video["source"] == "user-supplied private recording",
             "motor video provenance is not explicit")
    _require(video["raw_video_published"] is False, "private raw video was published")
    _require(video["synchronized_with_uart_capture"] is False,
             "private video must not be represented as synchronized UART evidence")
    _require_digest(video["sha256"], "motor video")
    _require(video["sha256"] ==
             "61894decd5d1fba15ed06aa58a3b2e25409157496334c1216f57e7968aafee54",
             "motor video digest changed")
    _require(video["bytes"] == 6020451 and video["resolution"] == [1920, 1080] and
             video["average_frame_rate"] == "115800/3863",
             "motor video media identity changed")
    _require(video["duration_seconds"] == 12.885617 and video["codec"] == "H.264",
             "motor video duration or codec changed")
    _require(len(video["direction_observations"]) == 4,
             "motor video does not contain four direction observations")
    actual_video_observations = [
        (
            item["channel"], item["corner"], tuple(item["interval_seconds"]),
            tuple(item["axis_angles_deg_mod_180"]), item["rotation"],
        )
        for item in video["direction_observations"]
    ]
    _require(actual_video_observations == EXPECTED_VIDEO_OBSERVATIONS,
             "motor video measurements or direction mapping changed")

    imu = record["imu"]
    _require(imu["transform"] == {
        "body_x": "sensor_y", "body_y": "sensor_x", "body_z": "-sensor_z"
    }, "IMU body transform changed")
    accel = imu["stationary_accel_mean_mps2"]
    gyro = imu["stationary_gyro_mean_dps"]
    _require(len(accel) == 3 and len(gyro) == 3 and
             all(math.isfinite(value) for value in accel + gyro),
             "IMU stationary means are incomplete or non-finite")
    _require(accel == EXPECTED_ACCEL_MEAN and gyro == EXPECTED_GYRO_MEAN,
             "stationary IMU means changed")
    _require(imu.get("stationary_accel_pstdev_mps2") == EXPECTED_ACCEL_PSTDEV and
             imu.get("stationary_gyro_pstdev_dps") == EXPECTED_GYRO_PSTDEV,
             "stationary IMU deviations changed")
    gravity_norm = math.sqrt(sum(value * value for value in accel))
    _require(accel[2] < -8.5 and 8.5 <= gravity_norm <= 10.5,
             "stationary gravity does not establish negative body Z")
    _require(imu["accel_samples"] == 18 and imu["gyro_samples"] == 44,
             "stationary IMU sample counts changed")
    _require(abs(imu["gravity_norm_mps2"] - gravity_norm) < 1e-8,
             "stored gravity norm does not match the sample mean")
    gravity_percent = (gravity_norm / 9.80665 - 1.0) * 100.0
    _require(abs(imu["gravity_relative_to_standard_percent"] - gravity_percent) < 1e-8,
             "stored gravity percentage does not match the sample mean")
    _require(imu["bias_correct_gyro"] is True and imu["zero_gyro_during_arming"] is True,
             "runtime gyro calibration is not enabled")
    _require(imu["stored_accel_bias"] == [0.0, 0.0, 0.0] and
             imu["stored_accel_scale"] == [1.0, 1.0, 1.0],
             "stored accelerometer calibration boundary changed")
    _require(imu["six_face_accelerometer_calibration_performed"] is False,
             "six-face calibration must not be inferred from one pose")
    _require(imu["acceptance_scope"] == "initial controlled attitude/rate flight",
             "IMU acceptance scope is broader than the measured evidence")
    gravity_roll = -math.degrees(math.atan2(accel[1], -accel[2]))
    gravity_pitch = math.degrees(
        math.atan2(accel[0], math.sqrt(accel[1] ** 2 + accel[2] ** 2))
    )
    _require(abs(imu["gravity_inferred_roll_deg"] - gravity_roll) < 1e-8 and
             abs(imu["gravity_inferred_pitch_deg"] - gravity_pitch) < 1e-8,
             "stored gravity attitude does not derive from the sample mean")
    _require(imu["attitude_roll_deg"] == -3.9381446838 and
             imu["attitude_pitch_deg"] == 0.1167451888,
             "live stationary attitude changed")
    _require(abs(gravity_roll - imu["attitude_roll_deg"]) < 1.0 and
             abs(gravity_pitch - imu["attitude_pitch_deg"]) < 1.0,
             "attitude does not agree with the stationary gravity vector")

    limitations = record["not_established"]
    _require(limitations == EXPECTED_LIMITATIONS,
             "remaining flight boundary changed")
    normalized = " ".join(str(item) for item in limitations).casefold()
    for phrase in ("battery-powered", "six-face", "propeller", "free flight"):
        _require(phrase in normalized, f"remaining boundary omits {phrase}")

    return {
        "status": "PASS",
        "arming_policy": arming["policy"],
        "peak_motor_channels": peaks,
        "motor_directions": len(video["direction_observations"]),
        "terminal_state": "DISARMED_ZERO",
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(f"usage: {Path(sys.argv[0]).name} EVIDENCE.json", file=sys.stderr)
        return 64
    try:
        result = validate_record(_load(Path(args[0])))
    except (EvidenceError, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"evidence error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
