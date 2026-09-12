# Attitude trace v2 semantics

The diagnostic object is 120 bytes, version 2, object ID `0xC6CEDB44`.
Its decoder must not be used against the earlier 96-byte firmware object.

- `PreBias` is the averaged, scaled and board-rotated gyro sample immediately
  before adaptive bias application. It is not a raw register measurement.
- `AppliedBias` is the effective floating-point difference between the gyro
  after bias application and `PreBias`. It is not a later snapshot of the
  bias parameter; rounding can make those values differ.
- Capture validity is cleared at sensor-update entry. No-data and read-only
  early returns cannot reuse the preceding sample. A valid sample is consumed
  once by the estimator trace hook.
- PWM remains an independently sampled software observation, not electrical
  feedback or proof of physical rotation.

These additions diagnose the normal-mixer gyro event without changing PID
settings, filtering, motor limits or the flight-control arithmetic.
Build and host tests alone do not establish deployment or flight readiness.
