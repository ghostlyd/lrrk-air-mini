"""Deterministic, fail-closed preflight analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

from .models import TelemetrySnapshot


@dataclass(frozen=True)
class SafetyPolicy:
    max_link_age_ms: float = 500.0
    max_future_skew_ms: float = 5000.0
    min_battery_voltage_v: float = 3.30
    warn_battery_percent: float = 20.0
    accepted_imu_identities: Tuple[str, ...] = ("MPU6050", "0x68", "0x69", "104", "105")


@dataclass(frozen=True)
class Finding:
    finding_id: str
    status: str
    severity: str
    evidence: str
    remediation: str

    def __post_init__(self) -> None:
        if self.status not in ("PASS", "WARN", "BLOCK", "UNKNOWN"):
            raise ValueError("invalid finding status")
        if self.severity not in ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"):
            raise ValueError("invalid finding severity")

    def to_dict(self) -> Dict[str, str]:
        return {
            "finding_id": self.finding_id,
            "status": self.status,
            "severity": self.severity,
            "evidence": self.evidence,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class PreflightReport:
    snapshot_hash: str
    generated_at: datetime
    analyzer_version: str
    overall: str
    findings: Tuple[Finding, ...]

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        if self.overall not in ("PASS", "INCOMPLETE", "BLOCKED"):
            raise ValueError("invalid preflight outcome")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_hash": self.snapshot_hash,
            "generated_at": self.generated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "analyzer_version": self.analyzer_version,
            "overall": self.overall,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def _finding(
    finding_id: str,
    status: str,
    severity: str,
    evidence: str,
    remediation: str,
) -> Finding:
    return Finding(finding_id, status, severity, evidence, remediation)


def _now(now: Optional[datetime]) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value


def _link_finding(snapshot: TelemetrySnapshot, policy: SafetyPolicy, elapsed_ms: float) -> Finding:
    age = snapshot.link_age_ms
    if age is None:
        return _finding("link.freshness", "UNKNOWN", "HIGH", "link age is unknown", "Establish a fresh telemetry link before flight.")
    age += elapsed_ms
    if age > policy.max_link_age_ms:
        return _finding("link.freshness", "BLOCK", "CRITICAL", "link age %.1f ms exceeds %.1f ms" % (age, policy.max_link_age_ms), "Reconnect telemetry and keep the aircraft disarmed.")
    return _finding("link.freshness", "PASS", "INFO", "link age %.1f ms" % age, "No action required.")


def _imu_findings(snapshot: TelemetrySnapshot, policy: SafetyPolicy) -> Iterable[Finding]:
    health = snapshot.sensors
    if health.imu_present is False:
        yield _finding("imu.presence", "BLOCK", "CRITICAL", "MPU6050 is reported absent", "Connect and verify the required MPU6050 before arming.")
    elif health.imu_present is None:
        yield _finding("imu.presence", "UNKNOWN", "HIGH", "IMU presence is unknown", "Read the target sensor status before arming.")
    else:
        yield _finding("imu.presence", "PASS", "INFO", "IMU is reported present", "No action required.")

    if health.imu_identity is None:
        yield _finding("imu.identity", "UNKNOWN", "HIGH", "MPU6050 identity is unknown", "Probe WHO_AM_I and record the result.")
    elif health.imu_identity not in policy.accepted_imu_identities:
        yield _finding("imu.identity", "BLOCK", "CRITICAL", "unexpected IMU identity %s" % health.imu_identity, "Stop and verify the sensor path and board revision.")
    else:
        yield _finding("imu.identity", "PASS", "INFO", "IMU identity %s" % health.imu_identity, "No action required.")

    if health.imu_healthy is False:
        yield _finding("imu.health", "BLOCK", "CRITICAL", "IMU health is faulted", "Keep outputs disabled and inspect the sensor transport.")
    elif health.imu_healthy is None:
        yield _finding("imu.health", "UNKNOWN", "HIGH", "IMU health is unknown", "Collect a fresh, valid sensor sample.")
    else:
        yield _finding("imu.health", "PASS", "INFO", "IMU health is nominal", "No action required.")


def _battery_findings(snapshot: TelemetrySnapshot, policy: SafetyPolicy) -> Iterable[Finding]:
    battery = snapshot.battery
    if battery.voltage_v is None and battery.percent is None:
        yield _finding("battery.availability", "UNKNOWN", "HIGH", "battery state is unknown", "Read battery voltage before arming.")
        return
    if battery.voltage_v is not None:
        if battery.voltage_v < 0:
            yield _finding("battery.voltage", "BLOCK", "CRITICAL", "negative battery voltage observed", "Reject the telemetry source and inspect the ADC path.")
        elif battery.voltage_v < policy.min_battery_voltage_v:
            yield _finding("battery.voltage", "BLOCK", "CRITICAL", "battery voltage %.2f V is below %.2f V" % (battery.voltage_v, policy.min_battery_voltage_v), "Disconnect and recharge or replace the battery.")
        else:
            yield _finding("battery.voltage", "PASS", "INFO", "battery voltage %.2f V" % battery.voltage_v, "No action required.")
    else:
        yield _finding("battery.voltage", "UNKNOWN", "HIGH", "battery voltage is unknown", "Read the battery ADC before arming.")
    if battery.percent is not None:
        if battery.percent < 0 or battery.percent > 100:
            yield _finding("battery.percent", "BLOCK", "HIGH", "battery percentage is outside 0..100", "Reject the telemetry source and inspect the battery estimator.")
        elif battery.percent < policy.warn_battery_percent:
            yield _finding("battery.percent", "WARN", "MEDIUM", "battery percentage %.1f%% is low" % battery.percent, "Use a charged battery for any powered test.")
        else:
            yield _finding("battery.percent", "PASS", "INFO", "battery percentage %.1f%%" % battery.percent, "No action required.")


def _actuator_finding(snapshot: TelemetrySnapshot) -> Finding:
    for index, value in enumerate(snapshot.actuators):
        if not math.isfinite(value) or value < 0 or value > 1000:
            return _finding("actuators.range", "BLOCK", "CRITICAL", "actuator %d has unsafe value %s" % (index, value), "Stop and keep all brushed outputs at zero.")
    if len(snapshot.actuators) != 4:
        return _finding("actuators.availability", "UNKNOWN", "HIGH", "expected four motor observations; received %d" % len(snapshot.actuators), "Verify all four LiteWing channels; partial or ambiguous mappings are not complete evidence.")
    return _finding("actuators.range", "PASS", "INFO", "%d actuator values are within 0..1000" % len(snapshot.actuators), "No action required.")


def _mode_finding(snapshot: TelemetrySnapshot) -> Finding:
    mode = (snapshot.flight_mode or "").strip().lower()
    if not mode:
        return _finding("capabilities.mode", "UNKNOWN", "HIGH", "flight mode is unknown", "Read the current mode and its configured stabilization behavior before flight.")
    if mode in {"rate", "attitude", "stabilized", "manual"}:
        return _finding("capabilities.mode", "PASS", "INFO", "first-image attitude/rate mode does not require positioning hardware", "No action required.")
    if mode not in {"position_hold", "altitude_hold", "auto", "gps", "navigation"}:
        return _finding("capabilities.mode", "UNKNOWN", "MEDIUM", "flight mode %s is not in the target policy" % mode, "Keep the assistant advisory and verify the mode manually.")
    capabilities = {item.lower() for item in snapshot.capabilities}
    if not capabilities.intersection({"positioning", "gps", "optical_flow", "tof", "barometer"}):
        return _finding("capabilities.mode", "BLOCK", "HIGH", "mode %s requires optional positioning hardware that is not evidenced" % mode, "Use the first-image attitude/rate mode or verify the required module.")
    return _finding("capabilities.mode", "PASS", "INFO", "mode %s has a declared positioning capability" % mode, "No action required.")


def run_preflight(
    snapshot: TelemetrySnapshot,
    policy: SafetyPolicy = SafetyPolicy(),
    now: Optional[datetime] = None,
) -> PreflightReport:
    """Return a deterministic report; no network or hardware access occurs."""

    current = _now(now)
    findings = []
    future_ms = (snapshot.captured_at - current).total_seconds() * 1000.0
    elapsed_ms = max(0.0, -future_ms)
    if future_ms > policy.max_future_skew_ms:
        findings.append(_finding("time.freshness", "BLOCK", "HIGH", "snapshot is %.1f ms in the future" % future_ms, "Fix clock synchronization and reject the snapshot."))
    elif elapsed_ms > policy.max_link_age_ms:
        findings.append(_finding("time.freshness", "BLOCK", "HIGH", "snapshot is %.1f ms old" % elapsed_ms, "Collect a current snapshot; replay does not establish current readiness."))
    else:
        findings.append(_finding("time.freshness", "PASS", "INFO", "snapshot timestamp is usable", "No action required."))

    findings.append(_link_finding(snapshot, policy, elapsed_ms))
    if snapshot.armed is True:
        findings.append(_finding("flight.armed", "BLOCK", "CRITICAL", "aircraft is reported armed", "Disarm through the normal flight-controller path before preflight work."))
    elif snapshot.armed is False:
        findings.append(_finding("flight.armed", "PASS", "INFO", "aircraft is reported disarmed", "No action required."))
    else:
        findings.append(_finding("flight.armed", "UNKNOWN", "CRITICAL", "armed state is unknown", "Do not assume the aircraft is safe; verify the flight-controller state."))

    findings.extend(_imu_findings(snapshot, policy))
    findings.extend(_battery_findings(snapshot, policy))
    findings.append(_actuator_finding(snapshot))
    findings.append(_mode_finding(snapshot))
    if snapshot.alarms is None:
        findings.append(_finding("flight.alarms", "UNKNOWN", "HIGH", "alarm state is unknown", "Obtain a complete current alarm report; missing telemetry does not mean clear alarms."))
    elif snapshot.alarms and all(alarm.endswith(":Uninitialised") for alarm in snapshot.alarms):
        findings.append(_finding("flight.alarms", "UNKNOWN", "HIGH", "uninitialised alarm states: %s" % ", ".join(sorted(snapshot.alarms)), "Verify which subsystems are initialized and required; these states are not an all-clear report."))
    elif snapshot.alarms:
        findings.append(_finding("flight.alarms", "BLOCK", "HIGH", "reported alarms: %s" % ", ".join(sorted(snapshot.alarms)), "Resolve every reported alarm before any powered test."))
    else:
        findings.append(_finding("flight.alarms", "PASS", "INFO", "no alarms reported", "No action required."))

    if any(item.status == "BLOCK" for item in findings):
        overall = "BLOCKED"
    elif any(item.status == "UNKNOWN" for item in findings):
        overall = "INCOMPLETE"
    else:
        overall = "PASS"
    return PreflightReport(
        snapshot_hash=snapshot.snapshot_hash(),
        generated_at=current,
        analyzer_version="litewing-safety-3",
        overall=overall,
        findings=tuple(findings),
    )
