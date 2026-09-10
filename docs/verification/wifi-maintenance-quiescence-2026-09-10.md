# Cooperative Wi-Fi retirement for maintenance

Implementation: `1545c24`; integrated target build: `7689dc0`.

The command service now exposes trusted internal nonblocking stop and acquire
quiescence-query APIs. One atomic lifecycle word serializes launch reservation
with a permanent stop flag. Stop before creation inhibits launch; stop during
failed creation is not lost when creation unwinds. Successful creation remains
single-use until reboot, including when the task completes before its creator
returns.

The task polls stop during setup, receive/service work and randomness/reply
boundaries. Existing controller fault handling retires input. Cleanup retries
retain resources and admission state until socket close, AP teardown and guard
release complete. The task wipes local state before publishing quiescence and
does no resource/credential work afterward; RTOS self-deletion can still follow.
Quiescence does not release retained wireless ownership or prove stack memory
reclamation. It is not an immediate motor-stop guarantee or a Disarmed check.

## Verification and provenance

- The implementation worker stopped at a usage limit with uncommitted changes.
  The main agent inspected those changes, completed the API contract comments,
  and ran the tests before committing. No claim is made here that the interrupted
  worker completed its review or supplied a verified red-test record.
- The actual task/controller/receiver/crypto fixture passes 43 deterministic
  scenarios and two real C/Python UDP loopbacks. New cases exercise stop before
  launch, during creation success/failure, early task completion, queued task,
  AP readiness, mapping/RNG work, active traffic, and repeated teardown failure.
- Fixture boundaries assert that resource work and buffer wipes precede
  quiescence. A cleanup scenario remains nonquiescent beyond 2.5 seconds before
  succeeding; this does not implement the separate maintenance wait deadline.
- All seven Wi-Fi test methods pass with pinned SDK/crypto inputs supplied and
  no skips. These include the credential decoder/loader/store and AP lifecycle.
- ESP-IDF 5.3.2 build passes at `7689dc0`, app size `0xd4000` (17% space free),
  with persistence-link verification. No firmware was flashed.

Independent review of this lifecycle increment remains pending after the agent
interruption. The USB worker must enforce the approved bounded wait, Disarmed
checks, receiver reservation and no-write-on-timeout policy before calling the
store. The new stop API is not yet called by a USB provisioning path. PR #65
remains draft; no physical provisioning or flight qualification is implied.

## Dedicated receiver maintenance reservation

`3ba2880` adds separate BeginMaintenance/MaintenanceHeld/EndMaintenance APIs.
The existing handshake token's contract forbids waiting across network work,
so the maintenance worker must not reuse it for AP shutdown. Both token types
share a monotonic generation counter and exclude each other. Maintenance also
blocks direct wireless claims, USB unpack and persistence loads, and refuses
fresh receiver input, existing owners and in-flight writes/loads. No spinlock
is held across the caller's wait or storage operation. Checked release failure
retains exclusion; Held reports false during a regressed clock.

The new actual-receiver ASan/UBSan fixture failed before the APIs existed, then
passed wrong/stale/cross-kind token cases, startup/disarmed rejection, nested
reservation, in-flight write/load rejection, clock rollback/recovery, fresh
USB input, and existing ownership. All 20 previous receiver tests and seven
Wi-Fi methods also pass. ESP-IDF 5.3.2 build passes at `3ba2880`, app size
`0xd4030` with 17% free and persistence-link validation passing.

The reservation does not itself observe FlightStatus or police arbitrary local
setters. The worker must establish and recheck Disarmed and maintain its token
through storage. The worker/parser/host integration and independent review of
this reservation remain pending. No device operation occurred.
