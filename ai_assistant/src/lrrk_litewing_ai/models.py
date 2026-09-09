"""Versioned, JSON-safe telemetry models.

The models deliberately preserve unknown values as ``None``. They validate
types and finite numeric values, but leave actuator range decisions to the
deterministic safety analyzer so an out-of-range observation becomes an
auditable blocking finding instead of disappearing as a parse error.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


SCHEMA_VERSION = 1


def _finite(value: Optional[float], field_name: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be numeric or null" % field_name)
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError("%s must be finite" % field_name)
    return converted


def _optional_bool(value: Optional[bool], field_name: str) -> Optional[bool]:
    if value is not None and not isinstance(value, bool):
        raise ValueError("%s must be boolean or null" % field_name)
    return value


def _aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("%s must be timezone-aware" % field_name)
    return value


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SourceIdentity:
    adapter: str
    board: Optional[str] = None
    firmware: Optional[str] = None
    transport: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.adapter, str) or not self.adapter.strip():
            raise ValueError("source.adapter must be a non-empty string")

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "adapter": self.adapter,
            "board": self.board,
            "firmware": self.firmware,
            "transport": self.transport,
        }


@dataclass(frozen=True)
class Attitude:
    roll_deg: Optional[float] = None
    pitch_deg: Optional[float] = None
    yaw_deg: Optional[float] = None

    def __post_init__(self) -> None:
        for name in ("roll_deg", "pitch_deg", "yaw_deg"):
            _finite(getattr(self, name), "attitude.%s" % name)

    def to_dict(self) -> Dict[str, Optional[float]]:
        return {
            "roll_deg": self.roll_deg,
            "pitch_deg": self.pitch_deg,
            "yaw_deg": self.yaw_deg,
        }


@dataclass(frozen=True)
class BatteryState:
    voltage_v: Optional[float] = None
    percent: Optional[float] = None
    current_a: Optional[float] = None

    def __post_init__(self) -> None:
        for name in ("voltage_v", "percent", "current_a"):
            _finite(getattr(self, name), "battery.%s" % name)

    def to_dict(self) -> Dict[str, Optional[float]]:
        return {
            "voltage_v": self.voltage_v,
            "percent": self.percent,
            "current_a": self.current_a,
        }


@dataclass(frozen=True)
class SensorHealth:
    imu_present: Optional[bool] = None
    imu_identity: Optional[str] = None
    imu_healthy: Optional[bool] = None
    barometer_present: Optional[bool] = None
    optical_flow_present: Optional[bool] = None
    tof_present: Optional[bool] = None

    def __post_init__(self) -> None:
        for name in (
            "imu_present",
            "imu_healthy",
            "barometer_present",
            "optical_flow_present",
            "tof_present",
        ):
            _optional_bool(getattr(self, name), "sensors.%s" % name)
        if self.imu_identity is not None and not isinstance(self.imu_identity, str):
            raise ValueError("sensors.imu_identity must be a string or null")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "imu_present": self.imu_present,
            "imu_identity": self.imu_identity,
            "imu_healthy": self.imu_healthy,
            "barometer_present": self.barometer_present,
            "optical_flow_present": self.optical_flow_present,
            "tof_present": self.tof_present,
        }


@dataclass(frozen=True)
class TelemetrySnapshot:
    snapshot_id: str
    captured_at: datetime
    source: SourceIdentity
    link_age_ms: Optional[float] = None
    armed: Optional[bool] = None
    flight_mode: Optional[str] = None
    attitude: Attitude = Attitude()
    battery: BatteryState = BatteryState()
    sensors: SensorHealth = SensorHealth()
    alarms: Tuple[str, ...] = ()
    actuators: Tuple[float, ...] = ()
    capabilities: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        _aware(self.captured_at, "captured_at")
        _finite(self.link_age_ms, "link_age_ms")
        if self.link_age_ms is not None and self.link_age_ms < 0:
            raise ValueError("link_age_ms must not be negative")
        _optional_bool(self.armed, "armed")
        if self.flight_mode is not None and not isinstance(self.flight_mode, str):
            raise ValueError("flight_mode must be a string or null")
        if not isinstance(self.attitude, Attitude) or not isinstance(self.battery, BatteryState):
            raise ValueError("attitude and battery must use their telemetry models")
        if not isinstance(self.sensors, SensorHealth):
            raise ValueError("sensors must use SensorHealth")
        for name, values in (("alarms", self.alarms), ("capabilities", self.capabilities)):
            if not isinstance(values, tuple) or not all(isinstance(item, str) and item for item in values):
                raise ValueError("%s must be a tuple of non-empty strings" % name)
        if not isinstance(self.actuators, tuple):
            raise ValueError("actuators must be a tuple")
        for index, value in enumerate(self.actuators):
            _finite(value, "actuators[%d]" % index)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": self.snapshot_id,
            "captured_at": _iso(self.captured_at),
            "link_age_ms": self.link_age_ms,
            "armed": self.armed,
            "flight_mode": self.flight_mode,
            "attitude": self.attitude.to_dict(),
            "battery": self.battery.to_dict(),
            "sensors": self.sensors.to_dict(),
            "alarms": list(self.alarms),
            "actuators": list(self.actuators),
            "capabilities": list(self.capabilities),
            "source": self.source.to_dict(),
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def snapshot_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "TelemetrySnapshot":
        if not isinstance(value, dict):
            raise ValueError("telemetry snapshot must be an object")
        if value.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
            raise ValueError("unsupported telemetry schema_version")
        required = ("snapshot_id", "captured_at", "source")
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError("telemetry snapshot missing: %s" % ", ".join(missing))
        captured_at = datetime.fromisoformat(str(value["captured_at"]).replace("Z", "+00:00"))
        source_value = value["source"]
        if not isinstance(source_value, dict):
            raise ValueError("source must be an object")
        attitude_value = value.get("attitude") or {}
        battery_value = value.get("battery") or {}
        sensors_value = value.get("sensors") or {}
        if not all(isinstance(item, dict) for item in (attitude_value, battery_value, sensors_value)):
            raise ValueError("attitude, battery, and sensors must be objects")
        return cls(
            snapshot_id=value["snapshot_id"],
            captured_at=captured_at,
            source=SourceIdentity(
                adapter=source_value.get("adapter"),
                board=source_value.get("board"),
                firmware=source_value.get("firmware"),
                transport=source_value.get("transport"),
            ),
            link_age_ms=value.get("link_age_ms"),
            armed=value.get("armed"),
            flight_mode=value.get("flight_mode"),
            attitude=Attitude(**attitude_value),
            battery=BatteryState(**battery_value),
            sensors=SensorHealth(**sensors_value),
            alarms=tuple(value.get("alarms") or ()),
            actuators=tuple(value.get("actuators") or ()),
            capabilities=tuple(value.get("capabilities") or ()),
        )

    @classmethod
    def from_json(cls, value: str) -> "TelemetrySnapshot":
        return cls.from_dict(json.loads(value))
