# PWM diagnostics implementation status

Approved scope: read-only USB observations of requested duty, successfully
submitted hardware duty, suppression conditions, and hardware-call errors.
Arming, throttle limits, and failsafe behavior must remain unchanged.

Branch: `codex/pwm-output-diagnostics`, based on merged main `71e4464`.

## Implemented, not deployed

The brushed PWM driver now provides a zero-wait, mutex-coherent observation.
Requested values are the last frame consumed by `PIOS_Servo_Update`, not a
partially staged frame. Submitted values record successful LEDC update/stop
calls in 11-bit units. A per-channel validity mask identifies unknown output
after a failed hardware call. These are API results, not measured electrical
duty or RPM. Counters saturate rather than wrapping.

Suppression reports hardware readiness, IMU health, output-update freshness,
the arming state last consumed by the output driver, failsafe, and shutdown.
Output-update freshness is NOT the receiver's independent lease status.

Validation: production-driver native suite, 14 tests passed. New cases cover
request versus commit, read-only snapshot behavior, IMU suppression, partial
hardware update failure, and failed stop producing an unknown channel.
Existing shutdown, watchdog, disarm, staging, and hardware-error cases pass.

Independent driver-only review found no actionable defects. Its scope was the
four driver/header/test changes, not USB integration. The reviewer confirmed
that successful snapshots briefly hold the shared output mutex: zero-wait
acquisition does not imply zero scheduling impact. No on-device timing claim
is made. Contention coverage verifies no wait, output mutation, or destination
overwrite when the lock is busy.

## USB integration validation

- Generated request-only object `LiteWingPWMObservation` uses ID `0xA6453F6E`
  and metadata ID `0xA6453F6F`, with a versioned 36-byte payload. Both remote
  object and metadata writes are rejected. No polling task is added.
- Generation validates upstream/custom object and metadata collisions. Native
  tests exercise the packer, unavailable/expired observations, byte layout,
  registration failures, routing, and the Python decoder against C output.
- Broad port suite: 402 tests, OK with 21 environment-dependent skips. The
  targeted CI-equivalent generated-schema gate passed 28 tests with zero skips.
- ESP-IDF 5.3.2 compiled the production sources successfully: application size
  `0xD5E60`, leaving 16% of the application partition free. This was a disposable
  compile-validation snapshot, not an installed image or release identity.
- Independent whole-change review found no actionable defects.

## Remaining before use on the board

- Review and merge; flash only the verified application image and verify the
  installed image before a bounded bench test.
- Compare requested versus submitted output during the test. Do not infer
  electrical output or shaft rotation from successful peripheral API calls.

No firmware has been flashed for this change and no motor command was sent
during implementation. Physical motor movement remains unresolved.
