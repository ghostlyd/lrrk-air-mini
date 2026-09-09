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

from .models import Attitude, BatteryState, SourceIdentity, TelemetrySnapshot
from .uavtalk import UAVTalkError, UAVTalkFrame

ATTITUDE_STATE = 0xD7E0D964
FLIGHT_STATUS = 0xEF69B6BC
BATTERY_STATE = 0x26962352
_LAYOUTS = {ATTITUDE_STATE: struct.Struct("<7f"),
            FLIGHT_STATUS: struct.Struct("<8B"),
            BATTERY_STATE: struct.Struct("<7f2B")}
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
    if any(isinstance(value, float) and not math.isfinite(value) for value in values):
        raise UAVTalkError("object contains non-finite numeric values")
    fields = {}
    if frame.object_id == ATTITUDE_STATE:
        fields["attitude"] = Attitude(*values[4:7])
    elif frame.object_id == BATTERY_STATE:
        if values[8] not in (0, 1):
            raise UAVTalkError("invalid battery autodetection enum")
        fields["battery"] = BatteryState(voltage_v=values[0], current_a=values[1])
    else:
        bounds = (3, len(_MODES), 3, 3, 3, 2, 2, 2)
        if any(value >= limit for value, limit in zip(values, bounds)):
            raise UAVTalkError("invalid FlightStatus enum")
        # ARMING must never be represented as confirmed disarmed.
        fields["armed"] = values[0] != 0
        fields["flight_mode"] = _MODES[values[1]]
    digest = hashlib.sha256(frame.payload).hexdigest()[:16]
    return TelemetrySnapshot(
        snapshot_id="uavtalk-%08x-%s" % (frame.object_id, digest),
        captured_at=captured_at,
        source=SourceIdentity(adapter="uavtalk-capture-ac77304", transport="file-replay"),
        link_age_ms=None,
        **fields,
    )
