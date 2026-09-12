# Attitude-step trace

## Purpose and alternatives

Investigate the abrupt attitude change observed in props-off USB-powered bench
tests before qualifying a flight image. Host polling loses intermediate samples;
raising its rate caused a freshness abort. A continuous 500 Hz UART stream would
exceed the 57600 baud link. Use bounded onboard RAM capture and deferred retrieval.

## Contract

- Opt-in `CONFIG_LRRK_ATTITUDE_TRACE`, dependent on the bench output limiter.
  Disabled builds allocate no trace buffer and do not register its object.
- Capture at the end of each completed complementary-filter attitude update:
  device completion timestamp, sequence, estimator timestep, calibrated/averaged
  input acceleration and gyro, corrected gyro, resulting RPY, and an independently
  qualified, zero-wait PWM API snapshot. This is not raw register capture, an
  atomic cross-task sample, electrical feedback, or RPM evidence.
- Fixed 512-record RAM buffer. Retain the latest 64 pretrigger updates. First
  known, unsuppressed, nonzero PWM snapshot triggers collection of the remaining
  records (normally 448). With fewer than 64 pretrigger records, retain more post
  records to fill 512. Continue after output stops; freeze when full. No restart
  except reboot. No dynamic allocation, new task, flash write, or UART send in
  the attitude hook. Short critical sections protect buffer writes and reads;
  obtain the PWM snapshot before taking the trace lock.
- A read-only, manually requested multi-instance `LiteWingAttitudeTrace` exposes
  a 96-byte record. Instance is chronological index 0..511 in the frozen buffer.
  Until frozen, return only state/count/index metadata with zero sample fields.
  The object manager registers only its initial instance; target pack interception
  provides virtual records. Bulk ALL_INSTANCES is not the download interface.
- No motor, arming, PID, sensor configuration, or pose-abort changes.

## Verification and deployment

Native tests exercise wrap ordering, early trigger, freeze immutability, invalid
indexes and incomplete reads. Test the actual packer and generated schema and
adaptation. Build both the default and trace configurations. Independently review
before merge. Application-only deployment requires backup, exact readback and
marker verification. Only then run a bounded bench trial and retrieve frozen
records into private storage. A trace build is not flight-ready firmware.
