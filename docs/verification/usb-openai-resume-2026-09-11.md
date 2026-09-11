# USB-to-Mac OpenAI advisory verification

Date: 2026-09-11. Host source: `4c2799bfd10be872dfba89a3f9842dfcaf38e6fa`.

The operator selected reuse of the existing project key. A bounded reset-neutral
USB collector obtained one current aggregate from the connected WCH bridge.
Only telemetry handshake, selected object requests and acknowledgements were
sent. No modem-control reset, flash, settings, receiver or motor command was
issued. FlightStatus reported disarmed and the four mapped motor values were
zero. Physical battery state was not established by this check.

That aggregate was saved privately and then consumed by the existing JSONL CLI
with its live OpenAI provider. This is a captured-observation advisory test, not
continuous acquisition during inference. The Mac retained its internet route;
neither Ethernet nor internet networking on the drone was necessary.

The existing key was loaded into the child process environment without shell
evaluation, printing, rewriting, or sending it to the aircraft. SDK tracing was
disabled. Raw capture, snapshot, provider output and audit remain outside Git
in an owner-only directory, with files created mode 0600.

Results:

- Installed the declared Agents SDK 0.22.1 into the existing host environment;
  its resolved OpenAI SDK was 3.13.0. All nine provider SDK tests passed.
- `pip check` reported no broken requirements. Tests emitted non-fatal
  no-active-span diagnostics; this was not a warning-free run.
- The advisory CLI exited zero. It correctly returned BLOCKED for the captured
  observation, including stale data (about 51.5 seconds), reported alarms and
  unknown IMU information. It did not claim flight readiness.
- The four-event audit chain validated: snapshot_received, preflight_result,
  provider_request, provider_result. Provider outcome was completed, with zero
  action events and no matches from the existing audit secret-pattern scanner.

| Private artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| USB capture | 906 | `c9bc1275ef0f4b5eae241876584b22d96ede2ec6ca153851b34ee6ef59d63fc8` |
| Normalized snapshot | 1297 | `c93881da00a4d1837bf71c1f1af9fce946f10478e43f132acd702c8674ce788c` |
| Advisory audit | 5616 | `34d7d1ef9e83003014c45ebe465efe05f740742a525d64ecead4a84e6376909d` |

This verifies the existing tethered data-to-advice path and provider audit
events. It does not qualify the currently installed diagnostic firmware,
continuous USB acquisition, wireless control, sensor health, battery selection
or flight. The CLI's ordinary serial constructor still differs from the
reset-neutral diagnostic collector used here; integrating that proven access
method requires implementation and regression tests, not a documentation-only
claim that the launcher already uses it.

## Reset-neutral default transport implementation follow-up

The host package now contains the diagnostic POSIX descriptor implementation
and selects it by default in SerialTelemetryTransport after exact USB identity
validation. The injected legacy factory remains a test/integration seam, not
the normal CLI default. Enumeration still requires pyserial. Four added tests
cover framing-only terminal configuration, exclusive access with no modem-line
ioctl, partial writes, descriptor cleanup and the normal transport selection.
The initial tests failed before implementation; all 332 host tests subsequently
passed, including the real optional SDK tests. Expected negative-path output
and SDK no-active-span diagnostics were present.

A bounded hardware collection using the new normal constructor rejected an
invalid sync byte after initial frame synchronization. It closed the port and
did not produce an accepted aggregate. The private capture was retained; no
provider call, reset, flash or motor command was performed for this follow-up.
The console-enabled diagnostic image remains a possible source of mixed serial
traffic, not an established cause. Strict framing was not relaxed. Thus host
regression tests pass, but hardware acceptance of the normal path remains
incomplete. Continuous acquisition is still separate pending work.

### Bounded sustained acquisition

At host source `3aa82b6`, a further diagnostic held one normal reset-neutral
SerialTelemetryTransport open for 15.01 seconds. It used the existing strict
synchronizer throughout, one-second handshake intervals and 200 ms selected
object requests. It did not reopen/resynchronize after an error, relax CRC
validation, reset the board, send controls or invoke OpenAI.

The run received 66,385 bytes and 903 selected telemetry frames across all five
selected object IDs (counts in numeric ID order: 202, 89, 89, 449, 74). There
was no exception, and the stream ended at a frame boundary. Every observed
armed state was false and every observed mapped motor tuple was four zeros.
The capture remains private. This demonstrates bounded sustained acquisition
on this run, not an indefinite service or resolution of the earlier malformed
stream. Continuous acquisition feeding the advisory worker still needs to be
integrated and tested; this diagnostic is not that production service.
