# Flight qualification checkpoint — 2026-09-11

**Not flight-qualified.** The installed image is a BEN1 diagnostic build,
not the normal flight image. Earlier stationary-IMU acceptance is historical;
the subsequently captured gyro transient remains unexplained.

## Verified state

- [PR #89](https://github.com/ghostlyd/lrrk-air-mini/pull/89#issuecomment-5643226826)
  deployed the bounded attitude recorder. A normal-arming trial observed
  nonzero PWM, one-second cutoff, zero output, and timeout disarming. All 512
  frozen records were recovered with valid index/sequence/time ordering.
- [PR #90](https://github.com/ghostlyd/lrrk-air-mini/pull/90#issuecomment-5643299553)
  added readback of the seven startup sensor settings without changing their
  values. The installed application was built from `c65557c`, whose tree
  matches merged `85ea260`. Application SHA-256 is
  `c20581196b7c8448c2e70ac8f97a128d9271a5a7343a973eec9c51165fe710ca`.
  Exact application readback and preserved recovery/settings regions passed.
  Startup reached healthy attitude acquisition and a 64-record rolling trace,
  establishing successful configuration readback on that boot.
- The installed diagnostic retains the 200/1000 per-channel ceiling and
  nonrenewable 1000 ms interval. Normal yaw-right arming remains configured.
  The closing request-only observation was Disarmed with all twelve commands
  and four PWM observations zero. No motor commands were sent for PR #90.

## What the trace establishes

The PR #89 trace spans 1.011635 seconds, with trigger index 64. Gyro-Z reached
−284.391 degrees/second before the estimator's local correction. The largest
single yaw step was 0.546 degrees. Recorded estimator timestep was
1.873–2.025 ms; this is the upstream **averaged** timestep, not acquisition
time. Shorter gaps between completion timestamps occur during catch-up, so
bounded timestep values do not clear every possible timing defect.

Before the first large gyro event at index 104, maximum recorded submitted
PWM per channel was `[2, 2, 4, 2]` on the 0..2047 scale. At index 106,
requested duty was `[0, 639, 0, 636]`, with submitted PWM `[0, 409, 0, 409]`.
Thus the large recorded motor response followed the gyro event; an earlier
high-output sample was not recorded. These independently acquired PWM
snapshots do not prove continuous electrical output or motor RPM.

The input shows a brief decaying event, not merely a large estimator timestep.
It does **not** distinguish real angular motion, an electrical/sensor
disturbance, or an acquisition-path defect. Photos show helping-hand supports;
restraint must not be equated with measured zero angular motion. The owner
subsequently confirmed propellers removed. No further propeller confirmation
is inferred from the older photographs.

## Remaining work toward actual flight

1. Correlate the transient with physical observation, or acquire evidence
   that separates sensor/acquisition behavior from fixture movement. Do not
   suppress valid gyro rates or change PID/filter settings merely to pass a
   bench check.
2. Complete the requested ten-second observation with a matching bounded
   runner and firmware. The [ten-second profile](ten-second-bench-profile.md)
   is source-tested but has not been exercised on this board. The installed
   one-second image does not satisfy that request.
3. Qualify the arriving battery, connector/polarity, retention, and charging
   compatibility using the [parts record](../PARTS_SELECTION.md). Arrival was
   reported as pending; no subsequent battery label or connection is verified.
4. Deploy and verify the normal flight image after resolving the diagnostic
   finding. A BEN1 image with a shutdown timer is not a flight image.
5. Qualify the actual operator/control link, stop/link-loss behavior, and
   battery-powered prop-off operation before the separate controlled flight
   phase. USB advisory AI already has bounded live evidence; this does not
   establish a wireless pilot link or free flight.

Raw captures, configuration payloads, and backups remain private. This record
does not authorize purchases, wiring changes, or a new physical flight phase.
