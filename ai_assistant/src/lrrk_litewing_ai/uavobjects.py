"""Selected receive schemas at NinjaPilot ac77304a58de6c8bd552f94668b46903adb71cb2.

Layouts and IDs come from the generated flight UAVObject headers. A capture
does not identify the physical aircraft or establish current sensor health.
Each object produces a partial snapshot; unrelated observations are never
silently combined across time.
"""

from __future__ import annotations

import hashlib
import math
import struct
from datetime import datetime
from typing import Optional

from .models import Attitude, BatteryState, SensorHealth, SourceIdentity, TelemetrySnapshot
from .configuration import ConfigurationObservation, STABILIZATION_MODES, AIRFRAME_TYPES, THRUST_CONTROLS
from .uavtalk import UAVTalkError, UAVTalkFrame

ATTITUDE_STATE = 0xD7E0D964
FLIGHT_STATUS = 0xEF69B6BC
BATTERY_STATE = 0x26962352
SYSTEM_ALARMS = 0x6B7639EC
ACTUATOR_COMMAND = 0xB8229FE4
# Port schema v1: metadata 0xDA60A0C7 is not a telemetry observation.
LITEWING_IMU_HEALTH = 0xDA60A0C6
FLIGHT_MODE_SETTINGS = 0x4D896486
SYSTEM_SETTINGS = 0xD9D093B8
_LAYOUTS = {ATTITUDE_STATE: struct.Struct("<7f"),
            FLIGHT_STATUS: struct.Struct("<8B"),
            BATTERY_STATE: struct.Struct("<7f2B"),
            SYSTEM_ALARMS: struct.Struct("<25B"),
            ACTUATOR_COMMAND: struct.Struct("<12hHHB"),
            LITEWING_IMU_HEALTH: struct.Struct("<I5B"),
            FLIGHT_MODE_SETTINGS: struct.Struct("<5f3H33B"),
            SYSTEM_SETTINGS: struct.Struct("<4I2f22B")}
_ALARM_NAMES = ("SystemConfiguration", "BootFault", "OutOfMemory", "StackOverflow",
                "CPUOverload", "EventSystem", "Telemetry", "Receiver", "ManualControl",
                "Actuator", "Attitude", "Sensors", "Magnetometer", "Airspeed",
                "Stabilization", "Guidance", "PathPlan", "Battery", "FlightTime", "I2C", "GPS")
_ALARM_STATES = ("Uninitialised", "OK", "Warning", "Critical", "Error")
_EXTENDED_STATES = ("None", "RebootRequired", "FlightMode", "UnsupportedConfig_OneShot",
                    "BadThrottleOrCollectiveInputRange")
_MODES = ("manual", "stabilized1", "stabilized2", "stabilized3",
          "stabilized4", "stabilized5", "stabilized6", "autotune",
          "position_hold", "course_lock", "position_roam", "home_leash",
          "absolute_position", "return_to_base", "land", "path_planner",
          "poi", "auto_cruise")


def snapshot_from_frame(frame: UAVTalkFrame, captured_at: datetime) -> Optional[TelemetrySnapshot]:
    """Return a partial observation, or None for control/unsupported objects.

    captured_at is operator-supplied capture metadata, never the replay time.
    Device timestamp ticks cannot be converted into UTC without a clock model.
    """
    if frame.message_type not in (0x20, 0x22, 0xA0, 0xA2):
        return None
    layout = _LAYOUTS.get(frame.object_id)
    if layout is None:
        return None
    if frame.instance_id != 0:
        raise UAVTalkError("selected single-instance object has nonzero instance")
    if len(frame.payload) != layout.size:
        raise UAVTalkError("payload length does not match pinned object schema")
    values = layout.unpack(frame.payload)
    # LiteWing voltage-only producers use NaN for unmeasured battery fields.
    # Translate these to model None before serialization; never admit infinity
    # or relax non-finite handling for attitude/other object schemas.
    if any(isinstance(value, float) and not math.isfinite(value)
           and not (frame.object_id == BATTERY_STATE and math.isnan(value))
           for value in values):
        raise UAVTalkError("object contains non-finite numeric values")
    fields = {}
    if frame.object_id == FLIGHT_MODE_SETTINGS:
        # Five floats and three uint16 fields precede all 33 byte enums.
        enums = values[8:]
        bounds = (11,) + (len(STABILIZATION_MODES),) * 24 + (18,) * 6 + (2, 2)
        if any(value >= bound for value, bound in zip(enums, bounds)):
            raise UAVTalkError("invalid FlightModeSettings enum")
        fields['configuration'] = ConfigurationObservation(
            stabilization_slots=tuple(tuple(STABILIZATION_MODES[v] for v in enums[i:i + 4])
                                      for i in range(1, 25, 4)),
            flight_mode_settings_age_ms=0,
        )
    elif frame.object_id == SYSTEM_SETTINGS:
        # Validate the complete payload, then discard GUI data and aircraft name.
        airframe, thrust = values[6], values[27]
        if airframe >= len(AIRFRAME_TYPES) or thrust >= len(THRUST_CONTROLS):
            raise UAVTalkError("invalid SystemSettings enum")
        fields['configuration'] = ConfigurationObservation(
            airframe_type=AIRFRAME_TYPES[airframe], thrust_control=THRUST_CONTROLS[thrust],
            system_settings_age_ms=0,
        )
    elif frame.object_id == LITEWING_IMU_HEALTH:
        age, version, verified, who_am_i, seen, health = values
        if version != 1 or verified not in (0, 1) or seen not in (0, 1) or health not in (0, 1, 2):
            raise UAVTalkError("invalid LiteWingIMUHealth version or enum")
        sample_age = age if seen and age != 0xFFFFFFFF else None
        fields["sensors"] = SensorHealth(
            imu_present=True if verified else None,
            imu_identity="0x%02x" % who_am_i if verified else None,
            imu_healthy=(False if health == 2 else
                         True if health == 1 and verified and sample_age is not None else None),
            imu_sample_age_ms=sample_age,
        )
    elif frame.object_id == ATTITUDE_STATE:
        fields["attitude"] = Attitude(*values[4:7])
    elif frame.object_id == BATTERY_STATE:
        if values[8] not in (0, 1):
            raise UAVTalkError("invalid battery autodetection enum")
        fields["battery"] = BatteryState(
            voltage_v=None if math.isnan(values[0]) else values[0],
            current_a=None if math.isnan(values[1]) else values[1])
    elif frame.object_id == FLIGHT_STATUS:
        bounds = (3, len(_MODES), 3, 3, 3, 2, 2, 2)
        if any(value >= limit for value, limit in zip(values, bounds)):
            raise UAVTalkError("invalid FlightStatus enum")
        # ARMING must never be represented as confirmed disarmed.
        fields["armed"] = values[0] != 0
        fields["flight_mode"] = _MODES[values[1]]
    elif frame.object_id == SYSTEM_ALARMS:
        if any(v >= len(_ALARM_STATES) for v in values[:21]) or any(
                v >= len(_EXTENDED_STATES) for v in values[21:23]):
            raise UAVTalkError("invalid SystemAlarms enum")
        alarms = ["%s:%s" % (name, _ALARM_STATES[v])
                  for name, v in zip(_ALARM_NAMES, values[:21]) if v != 1]
        for index, name in enumerate(_ALARM_NAMES[:2]):
            if values[21 + index]:
                alarms.append("%s:%s" % (name, _EXTENDED_STATES[values[21 + index]]))
            if values[23 + index]:
                alarms.append("%s:SubStatus=%d" % (name, values[23 + index]))
        fields["alarms"] = tuple(alarms)
    elif frame.object_id == ACTUATOR_COMMAND:
        # The pinned LiteWing adapter owns channels 1..4, in brushed-duty units
        # despite the inherited XML's servo-pulse unit label. Do not clamp faults
        # or silently discard evidence of a different output mapping.
        fields["actuators"] = tuple(values[:4])
        alarms = ["ActuatorCommand:UnmappedChannel%d=%d" % (index + 1, value)
                  for index, value in enumerate(values[:12]) if index >= 4 and value != 0]
        if values[14]:
            alarms.append("ActuatorCommand:FailedUpdates=%d" % values[14])
        if alarms:
            fields["alarms"] = tuple(alarms)
        # A zero failure counter is not a complete SystemAlarms observation:
        # leave alarms unknown in the ordinary zero-failure case.
    digest = hashlib.sha256(frame.payload).hexdigest()[:16]
    return TelemetrySnapshot(
        snapshot_id="uavtalk-%08x-%s" % (frame.object_id, digest),
        captured_at=captured_at,
        source=SourceIdentity(adapter="uavtalk-capture-ac77304", transport="file-replay"),
        link_age_ms=None,
        **fields,
    )
