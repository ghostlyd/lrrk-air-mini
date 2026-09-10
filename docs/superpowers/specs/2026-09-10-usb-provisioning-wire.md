# USB provisioning integration contract

Implementation refinement of the approved maintenance workflow in
`docs/verification/wifi-provisioning-boundary-2026-09-10.md`. The operator approved
that workflow on 2026-09-10. These messages are not implemented by this document.

## Framing and authority

Use the selected pinned UAVTalk dialect on the existing USB UART. It has a
10-byte untimestamped header, little-endian object and instance fields, and a
trailing CRC-8. CRC is corruption detection, not authentication: local serial
access is the maintenance authority. This interface must not be reachable
through the wireless pilot socket or an AI command tool.

Reserve unregistered IDs `0x4C575046` for provisioning submission and
`0x4C575048` for status. These values were not found in the currently generated
UAVObjects or repository source during the integration audit. A build/runtime
collision check is still required; never shadow a registered object. Do not
register a readable secret-bearing UAVObject.

Submission accepts only untimestamped OBJ_ACK (`0x22`), instance zero, and exactly
152 payload bytes: a nonzero 16-byte host-generated random transaction ID,
followed by the existing 136-byte LWCF v1 blob. The declared frame size is 162
bytes, with a separate trailing CRC (163 bytes total). Other types, instances,
lengths, malformed blobs, zero IDs and invalid CRC must not enqueue storage.

Reserved-frame assembly has a two-second total acceptance lifetime from SYNC,
not a sliding inactivity timeout. Check expiry on data and idle feeds and after
blocking lookups before dispatch. Cleanup is cooperative with the UART task;
the deadline does not guarantee erasure of every RAM copy within two seconds.

An ACK means only accepted for asynchronous processing. A NACK means this
submission was not accepted; it is not a statement about the outcome of any
earlier request. A lost ACK is ambiguous. No submission response echoes the
payload or credentials. No implicit reset occurs.

## Public status payload

Only an untimestamped OBJ_REQ (`0x21`), instance zero and empty payload may
request status. Respond with untimestamped OBJ (`0x20`), status object ID and
instance zero. The payload is exactly 24 bytes:

| Offset | Meaning |
| --- | --- |
| 0 | Version, exactly 1 |
| 1 | Phase: 0 unavailable, 1 idle, 2 queued, 3 waiting for stop, 4 storing, 5 cleanup blocked, 6 finished |
| 2 | Persistence result: 0 not attempted, 1 invalid, 2 not written, 3 uncertain, 4 verified |
| 3 | Reserved zero |
| 4–19 | Current/last accepted transaction ID; all zero before any accepted request |
| 20–23 | Reserved zero |

The status frame's declared size is 34 bytes plus one CRC byte. It contains no
SSID, password, application key, key-derived fingerprint, device identifier or
raw log data. Phase and persistence result are separate: verified persistence
with cleanup blocked is not a failed write and is not ready for rebootless use.
The host rejects unknown values, wrong lengths, nonzero reserved bytes and
statuses whose transaction ID differs from its pending request.

## Single pending request and asynchronous worker

Use one bounded mailbox, not an unbounded queue. The parser copies an accepted
request into owned storage and returns without NVS operations or waiting on
shutdown. The maintenance worker waits outside UART/parser connection locks.
Do not hold a spinlock while obtaining UAVObjects, stopping AP, sleeping or
accessing flash.

While a request is pending, reject additional submissions without overwriting
the mailbox. The host resolves a lost ACK by polling status; it does not
automatically retransmit the write. Retain the last accepted ID/result after
completion. Reject re-submission of that same ID, including changed contents;
status polling remains available. A deliberately retried uncertain transaction
uses a new ID but the exact previously saved credential blob. New accepted
transactions may replace the last result; callers must serialize provisioning.

Worker ordering:

1. Atomically observe Disarmed and acquire an arming-inhibit token using the
   object manager's existing mutex. Nonblocking lock acquisition must deny the
   transaction if busy. Inhibit Armed/Arming writes at the actual full-object,
   field and unpack mutation sites, while allowing Disarmed and unrelated writes.
   Then obtain a dedicated receiver maintenance reservation, which
   excludes fresh receiver input, another reservation, a wireless owner and
   in-flight USB writes/loads. Recheck the arming token and Disarmed under the
   same object mutex; a snapshot without write exclusion is insufficient.
2. Request cooperative Wi-Fi stop. Wait at most 2 seconds on a monotonic clock
   for quiescence; invalid/regressing time or timeout denies storage. Quiescence
   means no further resource/credential work, not proof that RTOS reclaimed
   the task stack. Do not force-delete the task or release wireless ownership.
3. Recheck Disarmed and the transaction's reservation before calling the scoped
   store exactly once. No late completion may revive a timed-out request.
4. Record the store result, wipe pending credentials, and release only this
   transaction's receiver reservation followed by its arming token using checked
   token APIs. Retain arming inhibition while receiver cleanup is blocked. If release fails,
   retain its cleanup context, publish cleanup blocked, and retry only cleanup.
   Do not repeat the credential write. Reject new provisioning until cleanup
   finishes. Radio restart stays inhibited until an explicit reboot.

Use `PIOS_LiteWing_GCSReceiver_BeginMaintenance`, `MaintenanceHeld`, and
`EndMaintenance` together with `lw_arming_maintenance_begin`, `held`, and `end`.
Arming tokens serialize against FlightStatus mutation using the object-manager
mutex, not the receiver spinlock. No mutex remains held across shutdown or NVS.
The short handshake admission token remains separate and
must not be held across shutdown waits. Both token kinds share the monotonic
generation counter and mutually exclude each other. Verify maintenance use
against the actual controller/receiver tasks; its name alone does not prove exclusion.
Reservation loss must deny the write; the worker never repairs it by clearing
some other owner's token.

## Secret handling and host recovery

Generate independent CSPRNG application and AP credentials and a non-identifying
SSID on the host. Durably save a private pending bundle outside repositories
before serial transmission. Keep the previous bundle during rotation. A timeout,
disconnect or mismatched status means unknown outcome, not permission to delete
either bundle. Promote only after verified persistence and completed cleanup.
Promotion retains an exclusive private `.stored` copy; pending and older copies
remain available. This records the local storage workflow, not active radio
credentials. Repeat reconciliation validates the existing copy without replacing
it. A local promotion failure must not trigger another credential submission.
An explicit reboot and authenticated connection separately verify activation.

Do not route outbound submissions through audit capture or model tools. Wipe
owned firmware request/parser buffers on rejection, completion and timeout;
audit partial/CRC-error paths too. SDK UART ring copies and Python immutable
objects preclude a blanket RAM-erasure claim. Core dumps must remain disabled;
old dumps and plaintext NVS keep their documented limitations.

Required tests cover exact C/Python frame vectors, fragmented and corrupt
requests, reserved-ID collision, no secret echo, queue saturation, lost ACK,
wrong/stale transaction status, armed and retained-owner rejection, pending
admission races, shutdown timeout/late exit, failed token cleanup, storage
uncertainty, and host private-file failure before transmission. Synthetic tests
do not replace later authorized physical provisioning and power-loss recovery.
