"""Validate a sanitized record of the bounded USB arm/motor proof.

This module reads ordinary JSON only.  It cannot open a serial device, write a
UAVObject, or emit a motor command.  The private UART capture remains outside
the repository; the committed record contains its digest and selected decoded
observations.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Sequence


SCHEMA = "lrrk.litewing.armed-motor-evidence.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_LOW = [1000, 1500, 1500, 1500, 1000, 1500, 1500, 1500]
EXPECTED_PULSE = [1510, 1500, 1500, 1500, 1000, 1500, 1500, 1500]
EXPECTED_EVIDENCE_ID = "litewing-usb-armed-nonzero-2026-09-09"
EXPECTED_CAPTURE_BYTES = 31912
EXPECTED_CAPTURE_SHA256 = "cce31d2ef701a230827b7b1cf54ca09124a9839ecb669f87a6144c5150b3fcf8"
EXPECTED_APPLICATION_SHA256 = "d7392031e9e06c39bcb503e0feb834942588b10b99cdfeeaa3248fbedae0ff31"
EXPECTED_PROBE_SHA256 = "0fea2cbcfba9bece72e2b62dd5f848386b4aeb5bec4c8ee6e2817aceefe62290"
EXPECTED_PROBE_TEST_SHA256 = "6c3c6337f461bb2ff884544ab041e96baed147acc8cb60c5d69d90a709988755"
EXPECTED_FLIGHT_REVISION = "ac77304a58de6c8bd552f94668b46903adb71cb2"
EXPECTED_PROBE_TESTS = 23
EXPECTED_DECODE_SHA256 = "f2cdc1c216929ddd0a19c8a496bc35b663d9cbfad03cfc6311d070087ff285ee"
EXPECTED_RECORD_SHA256 = "63d51842c894f93735c5398d35f96faeedbfee7ce2877a6af02a41910d30fa88"
EXPECTED_CLAIMS_NOT_ESTABLISHED = [
    "electrical PWM duty or cutoff timing",
    "physical motor rotation during this transaction",
    (
        "current RAM arming state after capture closure; Always Armed remains "
        "the conservative assumption until reset or power cycle and disarmed "
        "telemetry are verified"
    ),
    "arming state after a verified reset or power cycle",
    "battery-powered operation or flight readiness",
]


class EvidenceError(ValueError):
    """The evidence record is incomplete, inconsistent, or outside bounds."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _require_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} must be an object")
    _require(set(value) == expected, f"{label} fields do not match schema")
    return value


def _require_sha256(value: Any, label: str) -> str:
    _require(isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
             f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_int(value: Any, label: str, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum,
             f"{label} must be an integer >= {minimum}")
    return value


def _require_number(value: Any, label: str) -> float:
    _require(type(value) in (int, float) and math.isfinite(value),
             f"{label} must be a finite number")
    return float(value)


def _validate_event(event: Any, label: str, ceiling: int, nonzero: bool) -> dict[str, Any]:
    event = _require_keys(
        event,
        {
            "valid_frame", "motors", "flight_status", "arming",
            "receiver_connected", "throttle", "thrust",
        },
        label,
    )
    _require_int(event["valid_frame"], f"{label}.valid_frame", 1)
    motors = event["motors"]
    _require(isinstance(motors, list) and len(motors) == 4,
             f"{label}.motors must contain four channels")
    _require(all(type(value) is int and 0 <= value <= ceiling for value in motors),
             f"{label}.motors exceed the recorded command bound")
    _require(any(motors) if nonzero else motors == [0, 0, 0, 0],
             f"{label}.motors do not match the expected zero/nonzero state")
    _require(event["flight_status"] == "Armed",
             f"{label} was not observed while FlightStatus was Armed")
    _require(event["arming"] == "Always Armed",
             f"{label} was not observed with Always Armed selected")
    _require(type(event["receiver_connected"]) is bool,
             f"{label}.receiver_connected must be boolean")
    throttle = _require_number(event["throttle"], f"{label}.throttle")
    thrust = _require_number(event["thrust"], f"{label}.thrust")
    if nonzero:
        _require(event["receiver_connected"],
                 f"{label} nonzero command lacks a connected receiver sample")
        _require(0.0 < throttle <= 0.05 and 0.0 < thrust <= 0.05,
                 f"{label} receiver command is outside the bounded pulse")
    else:
        _require(throttle == -1.0 and thrust == -1.0,
                 f"{label} does not record the low/timeout command")
    return event


def validate_record(record: Any) -> dict[str, Any]:
    """Validate one v1 record and return its computed proof summary."""

    record = _require_keys(
        record,
        {
            "schema", "evidence_id", "scope", "capture", "provenance",
            "physical_conditions", "transaction", "decode", "limitations",
        },
        "record",
    )
    _require(record["schema"] == SCHEMA, "unsupported evidence schema")
    record_bytes = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    _require(hashlib.sha256(record_bytes).hexdigest() == EXPECTED_RECORD_SHA256,
             "sanitized record differs from the reviewed evidence payload")
    _require(record["evidence_id"] == EXPECTED_EVIDENCE_ID,
             "evidence_id does not identify the reviewed transaction")
    _require(isinstance(record["scope"], str) and record["scope"],
             "scope is required")

    capture = _require_keys(
        record["capture"],
        {"bytes", "sha256", "file_closed_at", "raw_capture_published"},
        "capture",
    )
    _require(capture["bytes"] == EXPECTED_CAPTURE_BYTES,
             "capture byte count does not match the reviewed transaction")
    _require_sha256(capture["sha256"], "capture.sha256")
    _require(capture["sha256"] == EXPECTED_CAPTURE_SHA256,
             "capture digest does not match the reviewed transaction")
    _require(capture["raw_capture_published"] is False,
             "the raw private capture must not be published")
    _require(isinstance(capture["file_closed_at"], str),
             "capture.file_closed_at is required")
    try:
        closed_at = datetime.fromisoformat(capture["file_closed_at"])
    except ValueError as exc:
        raise EvidenceError("capture.file_closed_at is not ISO-8601") from exc
    _require(closed_at.tzinfo is not None and closed_at.utcoffset() is not None,
             "capture.file_closed_at must include an offset")

    provenance = _require_keys(
        record["provenance"],
        {
            "installed_application_sha256", "probe_sha256",
            "probe_test_sha256", "probe_tests", "flight_source_revision",
            "decoder_boundary",
        },
        "provenance",
    )
    for field in (
        "installed_application_sha256", "probe_sha256", "probe_test_sha256"
    ):
        _require_sha256(provenance[field], f"provenance.{field}")
    _require(provenance["installed_application_sha256"] == EXPECTED_APPLICATION_SHA256,
             "installed application digest does not match the reviewed image")
    _require(provenance["probe_sha256"] == EXPECTED_PROBE_SHA256,
             "probe digest does not match the reviewed transaction")
    _require(provenance["probe_test_sha256"] == EXPECTED_PROBE_TEST_SHA256,
             "probe-test digest does not match the reviewed transaction")
    _require(isinstance(provenance["flight_source_revision"], str) and
             re.fullmatch(r"[0-9a-f]{40}", provenance["flight_source_revision"]) is not None,
             "flight source revision must be a full Git object id")
    _require(provenance["flight_source_revision"] == EXPECTED_FLIGHT_REVISION,
             "flight source revision does not match the reviewed UAVObject schema")
    _require(isinstance(provenance["decoder_boundary"], str) and
             provenance["decoder_boundary"], "decoder boundary is required")
    probe_tests = _require_keys(
        provenance["probe_tests"], {"passed", "failed"}, "provenance.probe_tests"
    )
    _require(probe_tests["passed"] == EXPECTED_PROBE_TESTS,
             "probe test count does not match the reviewed run")
    _require(probe_tests["failed"] == 0, "probe tests must have zero failures")

    conditions = _require_keys(
        record["physical_conditions"],
        {
            "propellers_removed", "contained", "battery_connected",
            "power_source", "usb_motor_power_acknowledged",
            "battery_absence_used_as_safety_interlock",
        },
        "physical_conditions",
    )
    _require(conditions["propellers_removed"] is True, "propellers were not confirmed removed")
    _require(conditions["contained"] is True, "containment was not confirmed")
    _require(conditions["battery_connected"] is False, "unexpected battery configuration")
    _require(conditions["power_source"] == "USB-C", "unexpected power source")
    _require(conditions["usb_motor_power_acknowledged"] is True,
             "USB motor capability was not acknowledged")
    _require(conditions["battery_absence_used_as_safety_interlock"] is False,
             "battery absence cannot be treated as a motor interlock")

    transaction = _require_keys(
        record["transaction"],
        {
            "persistent_write_sent", "restoration_skipped_by_request",
            "reset_sent_after_arm", "arming_field_before", "arming_field_terminal",
            "arming_scope", "receiver_low", "receiver_pulse", "receiver_period_ms",
            "pulse_deadline_ms", "command_scale", "command_ceiling",
        },
        "transaction",
    )
    _require(transaction["persistent_write_sent"] is False,
             "persistent settings write is outside this proof")
    _require(transaction["restoration_skipped_by_request"] is True,
             "record does not preserve the requested no-restore outcome")
    _require(transaction["reset_sent_after_arm"] is False,
             "record includes an unapproved reset after arming")
    _require(transaction["arming_field_before"] == "Always Disarmed" and
             transaction["arming_field_terminal"] == "Always Armed",
             "arming transition endpoints are inconsistent")
    _require(transaction["arming_scope"] == "RAM-only FlightModeSettings.Arming",
             "arming scope is not the reviewed RAM-only field change")
    _require(transaction["receiver_low"] == EXPECTED_LOW,
             "receiver_low is not the reviewed low frame")
    _require(transaction["receiver_pulse"] == EXPECTED_PULSE,
             "receiver_pulse is not the reviewed bounded frame")
    _require(transaction["receiver_period_ms"] == 40,
             "receiver period differs from the reviewed transaction")
    _require(0 < _require_int(transaction["pulse_deadline_ms"], "pulse deadline", 1) <= 800,
             "pulse deadline exceeds 800 ms")
    _require(transaction["command_scale"] == [0, 1000], "unexpected command scale")
    ceiling = _require_int(transaction["command_ceiling"], "command ceiling", 1)
    _require(ceiling <= 200, "command ceiling exceeds reviewed bound")

    decoded = _require_keys(
        record["decode"],
        {
            "valid_frames", "object_samples", "nonzero_actuator_samples",
            "post_nonzero_zero_samples", "terminal", "summary",
        },
        "decode",
    )
    decoded_bytes = json.dumps(
        decoded, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    _require(hashlib.sha256(decoded_bytes).hexdigest() == EXPECTED_DECODE_SHA256,
             "decoded observations differ from the reviewed sample set")
    valid_frames = _require_int(decoded["valid_frames"], "decode.valid_frames", 1)
    object_samples = _require_keys(
        decoded["object_samples"],
        {
            "FlightStatus", "ActuatorCommand", "FlightModeSettings",
            "ManualControlCommand", "SystemAlarms",
        },
        "decode.object_samples",
    )
    for name, count in object_samples.items():
        _require_int(count, f"decode.object_samples.{name}", 1)
        _require(count <= valid_frames, f"{name} count exceeds valid-frame count")

    nonzero_events = decoded["nonzero_actuator_samples"]
    _require(isinstance(nonzero_events, list) and len(nonzero_events) >= 3,
             "at least three nonzero actuator samples are required")
    for index, event in enumerate(nonzero_events):
        _validate_event(event, f"nonzero sample {index}", ceiling, True)
    nonzero_frames = [event["valid_frame"] for event in nonzero_events]
    _require(nonzero_frames == sorted(set(nonzero_frames)),
             "nonzero sample frame numbers must be strictly increasing")
    _require(nonzero_frames[-1] <= valid_frames,
             "nonzero sample frame exceeds the decoded capture")

    zero_events = decoded["post_nonzero_zero_samples"]
    _require(isinstance(zero_events, list) and len(zero_events) >= 3,
             "at least three post-pulse zero samples are required")
    for index, event in enumerate(zero_events):
        _validate_event(event, f"post-nonzero zero sample {index}", ceiling, False)
    zero_frames = [event["valid_frame"] for event in zero_events]
    _require(zero_frames == sorted(set(zero_frames)),
             "zero sample frame numbers must be strictly increasing")
    _require(zero_frames[0] > nonzero_frames[-1] and zero_frames[-1] <= valid_frames,
             "post-pulse zero evidence is out of sequence")
    _require(object_samples["ActuatorCommand"] >= len(nonzero_events) + len(zero_events),
             "selected actuator samples exceed the decoded object count")

    terminal = _validate_event(decoded["terminal"], "terminal", ceiling, False)
    _require(terminal == zero_events[-1],
             "terminal state must match the final post-pulse zero observation")
    _require(terminal["valid_frame"] == valid_frames,
             "terminal observation is not the final checksum-valid frame")
    _require(terminal["receiver_connected"] is False,
             "terminal receiver state was not timed out/disconnected")

    observed_peak = max(max(event["motors"]) for event in nonzero_events)
    peak_channels = next(
        event["motors"] for event in nonzero_events
        if max(event["motors"]) == observed_peak
    )
    summary = _require_keys(
        decoded["summary"],
        {
            "nonzero_motor_samples", "max_observed_motor_command",
            "peak_motor_channels", "post_nonzero_zero_samples", "terminal_state",
        },
        "decode.summary",
    )
    expected_summary = {
        "nonzero_motor_samples": len(nonzero_events),
        "max_observed_motor_command": observed_peak,
        "peak_motor_channels": peak_channels,
        "post_nonzero_zero_samples": len(zero_events),
        "terminal_state": "ARMED_ZERO_RECEIVER_TIMED_OUT",
    }
    _require(summary == expected_summary, "recorded summary does not match decoded samples")

    limitations = _require_keys(
        record["limitations"],
        {"terminal_scope", "claims_not_established"},
        "limitations",
    )
    _require(limitations["terminal_scope"] ==
             "last in-session telemetry; RAM arming may survive serial link closure while USB power remains",
             "terminal-state scope is missing or overstated")
    claims = limitations["claims_not_established"]
    _require(claims == EXPECTED_CLAIMS_NOT_ESTABLISHED,
             "limitations do not match the reviewed claim exclusions")

    return {"status": "PASS", **expected_summary}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args(argv)
    try:
        with args.record.open("r", encoding="utf-8") as stream:
            record = json.load(stream)
        result = validate_record(record)
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        print(f"evidence rejected: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
