"""Bounded neutral-only cleanup for an already-open bench connection.

Callbacks must use bounded/nonblocking I/O. This is telemetry evidence, not
electrical or RPM verification. No reset, arming, settings, or powered retry.
"""


def stop_and_confirm(*, clock, sleep, write, read, latest, neutral, requests):
    started = clock()
    deadline = started + 2.0
    next_neutral = next_request = started
    writes = 0

    def send(packet):
        nonlocal writes
        if clock() >= deadline:
            raise TimeoutError('cleanup deadline reached')
        if write(packet) != len(packet):
            raise RuntimeError('short cleanup write')
        writes += 1

    error = 'zero-output evidence timeout'
    confirmed = False
    try:
        while clock() < deadline:
            if clock() >= next_neutral:
                send(neutral)
                next_neutral = clock() + .04
            if clock() >= next_request:
                for packet in requests:
                    send(packet)
                next_request = clock() + .1
            read()
            current = clock()
            pwm, pt = latest.get('LiteWingPWMObservation', ({}, 0))
            motor, mt = latest.get('ActuatorCommand', ({}, 0))
            if (current < deadline and all(started < t <= current and
                    current-t <= .25 for t in (pt, mt)) and
                    pwm.get('available') is True and
                    pwm.get('submitted_ledc') == [0]*4 and
                    pwm.get('write_errors') == 0 and pwm.get('stop_errors') == 0 and
                    motor.get('Channel') == [0]*12 and
                    motor.get('NumFailedUpdates') == 0):
                confirmed = True
                error = None
                break
            sleep(min(.003, max(0, deadline-clock())))
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    return {'confirmed_zero': confirmed, 'error': error,
            'elapsed_s': clock()-started, 'checked_writes': writes}
