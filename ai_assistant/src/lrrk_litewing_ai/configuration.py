"""Immutable sampled settings from NinjaPilot ac77304, not flight authority."""

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


STABILIZATION_MODES = (
    'Manual', 'Rate', 'Attitude', 'AxisLock', 'WeakLeveling', 'VirtualBar',
    'Acro+', 'Rattitude', 'RelayRate', 'RelayAttitude', 'AltitudeHold',
    'AltitudeVario', 'CruiseControl',
)
AIRFRAME_TYPES = (
    'FixedWing', 'FixedWingElevon', 'FixedWingVtail', 'VTOL', 'HeliCP',
    'QuadX', 'QuadP', 'Hexa', 'Octo', 'Custom', 'HexaX', 'HexaH', 'OctoV',
    'OctoCoaxP', 'OctoCoaxX', 'OctoX', 'HexaCoax', 'Tri', 'GroundVehicleCar',
    'GroundVehicleDifferential', 'GroundVehicleMotorcycle',
)
THRUST_CONTROLS = ('Throttle', 'Collective', 'None')
SUPPORTED_ROTATIONAL_MODES = frozenset(('Rate', 'Attitude'))
CONFIGURATION_MAX_AGE_MS = 2000


@dataclass(frozen=True)
class ConfigurationObservation:
    stabilization_slots: Tuple[Tuple[str, str, str, str], ...] = ()
    airframe_type: Optional[str] = None
    thrust_control: Optional[str] = None
    flight_mode_settings_age_ms: Optional[float] = None
    system_settings_age_ms: Optional[float] = None

    def __post_init__(self) -> None:
        slots = self.stabilization_slots
        if not isinstance(slots, tuple) or len(slots) not in (0, 6):
            raise ValueError('stabilization_slots must be an empty tuple or six tuples')
        for slot in slots:
            if (not isinstance(slot, tuple) or len(slot) != 4
                    or any(not isinstance(v, str) or v not in STABILIZATION_MODES for v in slot)):
                raise ValueError('each stabilization slot must contain four pinned symbolic enums')
        for name, options in (('airframe_type', AIRFRAME_TYPES), ('thrust_control', THRUST_CONTROLS)):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or value not in options):
                raise ValueError('%s must be a pinned symbolic enum or null' % name)
        for name in ('flight_mode_settings_age_ms', 'system_settings_age_ms'):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError('%s must be finite, nonnegative numeric or null' % name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'stabilization_slots': [list(slot) for slot in self.stabilization_slots],
            'airframe_type': self.airframe_type,
            'thrust_control': self.thrust_control,
            'flight_mode_settings_age_ms': self.flight_mode_settings_age_ms,
            'system_settings_age_ms': self.system_settings_age_ms,
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> 'ConfigurationObservation':
        if not isinstance(value, dict):
            raise ValueError('configuration must be an object')
        slots = value.get('stabilization_slots', [])
        if not isinstance(slots, list) or any(not isinstance(slot, list) for slot in slots):
            raise ValueError('stabilization_slots must be an array of arrays')
        return cls(
            stabilization_slots=tuple(tuple(slot) for slot in slots),
            airframe_type=value.get('airframe_type'),
            thrust_control=value.get('thrust_control'),
            flight_mode_settings_age_ms=value.get('flight_mode_settings_age_ms'),
            system_settings_age_ms=value.get('system_settings_age_ms'),
        )
