# Inactive LiteWing actuator reporting correction

## Scope and authority

Correct the diagnosed producer mismatch in the approved OpenPilot port. The
binding contract is the existing four-output LiteWing backend and the pinned
upstream actuator algorithm. This is a bug fix, not a new arming policy.

## Global Constraints

- Preserve channels 1..4, active mixers, physically mapped outputs, non-PWM
  channel types, read-only command overrides, failure counters and alarms.
- Do not suppress host unmapped-output checks or modify stored settings.
- Do not change arming, watchdogs, IMU freshness, or flight-mode policy.
- No hardware access, network/provider calls, or secret access by the worker.
- Modify the hash-checked source adapter, never the pinned upstream checkout.

### Task 1: Normalize only demonstrably inactive actuator slots

In `ports/ninjapilot-litewing/prepare_control.py`, adapt the disabled-mixer
branch of the generated actuator task. Set the existing command activity flag
to zero only when the logical index is outside the four LiteWing outputs,
the mixer is Disabled, the channel type is ordinary PWM, and ChannelAddr is
outside the four physical outputs. Use the board contract constant rather
than duplicating the output count. The existing scaling loop should then
preserve zero for these inactive slots. Do not change any other branches or
the post-publication read-only object readback.

Test first using the actual adapted producer and generated objects through
the existing native thrust fixture. Default inactive tail slots must report
zero; remapped physical slots, active extra mixers and other channel types
must retain their behavior. Verify channels 1..4 and hardware writes, failure
counters/alarms, and read-only overrides are unchanged. Keep the host tests
that flag unexpected nonzero unmapped values. Extend existing fixtures when
practical; no broad refactoring or test-only production seams.

Run focused tests while iterating, then the covering thrust/preparation/startup
and host UAVObject/live collector tests before committing. Record the failing
pre-fix result, exact commands, passed/skipped counts, and any warning output.
Ensure existing strict CI executes the new behavioral cases; if existing suite
discovery already covers them, no workflow change is needed.

## Controller acceptance after Task 1

Review the task, run the complete branch review, build the exact committed
ESP-IDF candidate, and perform authorized application-only installation with
readback and persistence checks. Accept only observed inactive-tail correction
with unchanged four motor commands and no new errors. Keep hardware acceptance
separate from native tests and flight qualification.
