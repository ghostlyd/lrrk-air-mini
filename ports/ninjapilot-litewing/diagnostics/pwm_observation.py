"""Decode v1 request-only PWM observations; never opens a device.

Submitted values describe successful peripheral API calls, not measured
electrical duty or shaft speed. Snapshot age excludes transport delay; callers
must separately track receipt freshness. This decoder does not authorize motion.
"""
import struct

OBJECT_ID = 0xA6453F6E
WIRE_SIZE = 36
SUPPRESSION = (
    'hardware_unavailable', 'imu_unhealthy', 'output_update_stale',
    'driver_last_observed_disarmed', 'failsafe', 'shutdown',
)


def decode(payload):
    if not isinstance(payload, bytes) or len(payload) != WIRE_SIZE:
        raise ValueError('invalid PWM observation payload')
    values = struct.unpack('<4I8H4B', payload)
    age, commits, write_errors, stop_errors = values[:4]
    requested, submitted = values[4:8], values[8:12]
    version, available, mask, suppression = values[12:]
    if version != 1 or available not in (0,1) or mask > 15 or suppression > 63:
        raise ValueError('unsupported PWM observation validity')
    if any(v > 1000 for v in requested) or any(v > 2047 for v in submitted):
        raise ValueError('PWM observation duty out of range')
    if available and age >= 100:
        raise ValueError('PWM snapshot was stale before packing')
    if not available and (mask or suppression or commits or write_errors or
                          stop_errors or any(requested) or any(submitted)):
        raise ValueError('unavailable PWM snapshot contains valid-looking data')
    return {
        'available': bool(available),
        'snapshot_age_ms': None if age == 0xffffffff else age,
        'requested_duty': list(requested) if available else None,
        'submitted_ledc': [submitted[i] if available and mask & (1 << i)
                           else None for i in range(4)],
        'commits': commits if available else None,
        'write_errors': write_errors if available else None,
        'stop_errors': stop_errors if available else None,
        'suppression': [name for bit,name in enumerate(SUPPRESSION)
                        if suppression & (1 << bit)] if available else None,
    }
