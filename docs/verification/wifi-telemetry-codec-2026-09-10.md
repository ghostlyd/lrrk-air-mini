# Wi-Fi telemetry codec verification — 2026-09-10

Scope: wire-format implementation following design commit `3d5faa6` on
`codex/wifi-telemetry`. This is a source/host test milestone, not an operational
wireless link, flight-readiness finding or board acceptance record.

## Implementation

Python and C encode/decode the same bounded telemetry payload. A strict
telemetry wrapper adds LWPL direction 1/kind 8, nonzero session and sequence,
zero challenge, canonical length and authenticated bytes. The general LWPL
codec now recognizes kind 8 only in the board-to-host direction. Controller
admission and control-policy code are unchanged. C frame validation requires
an already authenticated frame; it does not itself verify a MAC.

Only the existing five pinned object layouts are accepted. Metadata checks
include INT64_MAX timestamp bounds and a distinct unknown sample-age sentinel.
Object data stays byte-exact; semantic enum/number validation is still required
at the existing snapshot parser boundary. Callers must supply the derived
telemetry key; arbitrary key bytes do not prove derivation or board identity.

## Executed checks

Local interpreter: Homebrew CPython 3.14.7. C compiler: local `cc`, strict C11
warnings treated as errors. New sanitizer harness uses ASan and UBSan.

| Check | Result |
| --- | --- |
| New Python telemetry tests | 6 passed |
| New actual-C telemetry tests | 7 passed, including sanitizer harness |
| Full host suite | 276 run; 267 passed; 9 optional SDK skips |
| Full port suite with pinned NinjaPilot source | 379 run; 358 passed; 21 optional environment skips |
| Actual pinned-mbedTLS session suite, separately enabled | 26 passed |
| Staged whitespace check | Passed |

Independent review of the implementation found no actionable severity
findings and judged it mergeable as a codec-only milestone. The reviewer also
ran the focused Python/C telemetry and pinned-mbedTLS session suites. Full-port
success above resolves the review's pending-suite condition.

Commands (checkout paths are operator-selected, not secrets):

```sh
PYTHONPATH=ai_assistant/src python3 -m unittest discover -s ai_assistant/tests
LRRK_TEST_FLIGHT_ROOT=/path/to/NinjaPilot python3 -m unittest discover -s ports/ninjapilot-litewing/tests
LRRK_TEST_MBEDTLS_ROOT=/path/to/esp-idf/components/mbedtls/mbedtls python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_pilot_session.py
```

NinjaPilot revision: `ac77304a58de6c8bd552f94668b46903adb71cb2`.
mbedTLS revision enforced by the session harness:
`98fcfd6d2cea90d306e8fde8e5bffd6087c9cda8`.
The full port run did not enable every optional external dependency; the
separate session run is evidence for that suite only, not all skipped tests.

## What the tests demonstrate

- Hand-written frozen payload and round trips across all five object layouts,
  zero/maximum timestamps and known/unknown age boundaries.
- C/Python byte-identical authenticated 136-byte datagram. C MAC callback uses
  Python standard-library HMAC in this cross-language test, not ESP-IDF hardware
  execution. The separate session suite compiles actual pinned mbedTLS.
- Root, c2b and b2c keys reject telemetry-key tags; all-byte tampering,
  truncation and trailing-byte rejection.
- Actual C bounds, error-output clearing, destination canaries, NULL handling,
  all undersized encoding capacities, and sanitizer checks through every
  uint16 frame payload length.
- Telemetry cannot create a pilot candidate or renew the accepted input-age
  origin in the real C session state machine, even when signed with c2b.

## Test-first and corrections

Before implementation, Python tests failed because `telemetry_wire` did not
exist; C tests failed the explicit missing-implementation assertion. They then
passed with the new modules. The full port suite's first invocation incorrectly
pointed the fixture root at `NinjaPilot/flight`, producing missing `flight/flight`
paths. Correcting the command to the checkout root produced the passing run;
no production workaround was added.

The new control-isolation test initially moved its fixture clock backward by
one microsecond on its second packet. The session correctly retired. Correcting
the test to monotonically increasing times proved rejection without changing
the firmware's clock-regression policy.

## Still required

This change does not wire the C codec into a firmware producer or activate it.
Session replay consumer, local credential handoff, host demultiplexer, coherent
sample timestamps, bounded producer scheduling and advisory-AI integration are
not yet implemented. No one-way timestamp or HMAC result establishes freshness.
Target build/integration, CI on the PR, board association, radio scheduling and
physical stop timing remain separate evidence. No serial device was opened,
no firmware flashed, and no provisioning, arming or motor command was sent.
