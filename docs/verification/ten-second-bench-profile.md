# Ten-second bench profile

The PWM driver now supports a build-time one-shot interval of 1–10 seconds.
The original bench profile still defaults to one second. The explicit
`sdkconfig.bench-ten-second.defaults` profile selects ten seconds with the
unchanged 200/1000 per-motor ceiling and BEN1 diagnostic identity.

The interval starts at the first eligible nonzero frame. Zero commands,
disarm/rearm and fresh receiver packets do not renew it. Output updates and
the watchdog enforce expiry; actual scheduling latency is not a guaranteed
electrical cutoff. IMU health, failsafe, stale updates and driver errors can
stop outputs earlier. This is not flight firmware.

Use a fresh SDKCONFIG when selecting the profile: defaults do not override
an existing generated configuration. Verify the resolved duration before build.

## Evidence boundary

Native tests execute the production driver with hardware/RTOS seams replaced.
They exercise fresh 40 ms updates through ten seconds, expiry on both update
and watchdog paths, the unchanged duty ceiling, and nonrenewal after rearming.
These tests are not electrical or motor-rotation evidence.

No ten-second image has been flashed or exercised on the board as part of this
change. The existing private host harness still has shorter transaction limits
and a separate tilt abort; it must not be represented as a ten-second runner.
The previously observed tilt transient remains unresolved. A longer firmware
deadline alone does not resolve it or establish flight readiness.
