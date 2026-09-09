"""Acceptance evidence for the disarmed native simulator, not for real flight."""

import math


class ProbeFailure(ValueError):
    pass


class Evidence:
    def __init__(self):
        self.counts = dict.fromkeys(("imu", "FlightStatus", "ActuatorCommand", "AttitudeState"), 0)
        self.latest = {}
        self.failure = None
        self.last_attitude = None

    def reject(self, message):
        self.failure = self.failure or message
        raise ProbeFailure(self.failure)

    def record(self, name, now):
        self.counts[name] += 1
        self.latest[name] = now

    def imu(self, values, now):
        if len(values) != 6 or not all(math.isfinite(v) for v in values):
            self.reject("nonfinite or malformed IMU")
        self.record("imu", now)

    def observe(self, name, data, now):
        if name == "FlightStatus":
            if data.get("Armed") != "Disarmed":
                self.reject("firmware is not disarmed")
        elif name == "ActuatorCommand":
            motors = data.get("Channel", [])
            if len(motors) < 4 or any(v != 0 for v in motors[:4]):
                self.reject("nonzero or missing motor outputs")
        elif name == "AttitudeState":
            angles = [data.get(k, float("nan")) for k in ("Roll", "Pitch", "Yaw")]
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in angles):
                self.reject("nonfinite or missing attitude")
            self.last_attitude = angles
        else:
            return
        self.record(name, now)

    def result(self, now):
        if self.failure:
            raise ProbeFailure(self.failure)
        for name, count in self.counts.items():
            minimum = 100 if name == "imu" else 10
            if count < minimum:
                raise ProbeFailure("insufficient %s samples: %d" % (name, count))
            if not 0 <= now - self.latest[name] <= 0.5:
                raise ProbeFailure("stale %s stream" % name)
        return {"status": "PASS", "counts": dict(self.counts), "last_attitude_deg": self.last_attitude}
