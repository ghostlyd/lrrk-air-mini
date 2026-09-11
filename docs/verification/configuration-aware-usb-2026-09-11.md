# Configuration-aware USB host acceptance

Host implementation: `aeeb7fa`, based on the approved configuration-aware design.
Installed board application remained `4fb4938`; this work did not flash firmware,
reset the board, alter saved settings, or invoke OpenAI.

## Same-image serial comparison

Both collectors used reset-neutral USB access at 57600 baud for 15 seconds.
The baseline was the previously installed host package; the extended collector
was loaded from the implementation worktree. RX and TX are separate directions.

| Measurement | Baseline | Configuration-aware |
| --- | ---: | ---: |
| Elapsed seconds | 15.0067 | 15.0092 |
| Received bytes | 70,905 | 72,864 |
| Transmitted bytes | 5,652 | 6,030 |
| Complete aggregates | 74 | 74 |
| Collection errors / mandatory timeouts | 0 / 0 | 0 / 0 |
| Initial synchronization bytes discarded | 50 | 66 |
| Aggregate IMU age min / median / max, ms | 1 / 8.385 / 45.061 | 1 / 8.439 / 96.358 |

Each settings object was requested 15 times. Minimum observed request intervals
were 1.000777 seconds for FlightModeSettings and 1.000747 seconds for
SystemSettings. No catch-up burst occurred. All 74 extended snapshots contained
configuration and correctly classified the observed Stabilized1 tuple
Attitude/Attitude/Rate/Manual on QuadX/Throttle as not requiring positioning
hardware. This is a mode-dependency finding, not an overall flight-ready result.

The aggregate rate was effectively unchanged, satisfying the approved maximum
10 percent reduction criterion. The maximum host-aggregate IMU age increased;
the existing 20 ms IMU-health policy was not relaxed. This run does not resolve
the separate timing/currentness issue or prove a hard scheduling bound. Initial
discard counts are explicit, not post-sync parser errors hidden by recovery.
Independent capture parsing found 1,890 baseline and 1,919 extended valid frames,
zero NACKs, and complete ending frame boundaries. Each capture contained 224
IMU-health reports; maximum board-reported sample age was 4 ms baseline and
2 ms extended. Board-reported sample age and host-aggregate age are distinct.

## Software validation

The implementation's full host suite passed 397 tests with no skips, with pinned
generator interoperability enabled. Tests cover complete wire layouts/enums,
all six slots, thrust dependencies, missing/stale data, schema 1/2 compatibility,
schema 3 serialization, approval invalidation, NACK revocation, connection
clearing, and slow polling without changing the mandatory telemetry cadence.
Independent task review approved specification compliance and code quality.

Raw captures and normalized runtime evidence remain private outside Git. No
aircraft name, USB topology, credentials, or provider content is published here.
