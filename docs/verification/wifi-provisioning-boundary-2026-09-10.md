# USB provisioning boundary audit

Source baseline: merged PR #62, `62333acf7a4d65c0961d0c63837c182d14e63abb`.
This is a source audit and proposed implementation boundary, not a provisioning
result. No board access, credential generation, flash, or motor operation occurred.

## Verified existing boundaries

- `target/pios_litewing_wifi_config.c` opens only `nvs/lw_pilot` read-only and
  reads exactly the bounded `config` blob. There is no credential writer.
- `prepare_uavtalk.py` adapts hash-pinned upstream input without modifying the
  external checkout. Existing writes use the receiver's guarded unpack path.
- Pinned upstream `uavtalk.c`, `UAVTalkProcess_INSTID`, accepts bounded payloads
  for unknown object IDs and checks declared lengths; CRC completion precedes
  `receiveObject`. Thus a target-only maintenance envelope is technically
  possible without registering a secret-bearing readable UAVObject.
- Unknown objects currently fail in `receiveObject`; adding a writer requires
  an explicit interception, not merely defining a new ID. Its immutable payload
  length, type, instance, and CRC-complete timestamp must reach the interceptor.
- `PIOS_LiteWing_GCSReceiver_BeginAdmission` excludes a wireless owner, fresh
  USB input, an existing reservation, and in-flight USB writes. It is not by
  itself a complete provisioning transaction: AP-task lifetime, pending
  sessions, flight state, and storage failure handling remain separate concerns.
- ESP-IDF 5.3.2's local `docs/en/api-reference/peripherals/spi_flash/
  spi_flash_concurrency.rst` documents cache/task/interrupt effects of flash
  access. A credential write must not be treated as an ordinary real-time
  pilot command. No radio timing qualification follows from NVS thread safety.
- The host's existing JSONL helper protects audit files, not credential
  provisioning. Reusing its append-only interface would be inappropriate for
  an atomic credential bundle and uncertain device-write recovery.

All `target` paths above are relative to `ports/ninjapilot-litewing`.

## Approaches

1. Recommended: explicit USB maintenance transaction while disarmed. Reserve
   receiver ingress, cooperatively stop and join the Wi-Fi command service,
   verify no retained owner and recheck Disarmed, then write only the dedicated
   credential key. Radio remains stopped until an explicit reboot. USB
   telemetry/recovery remains available; no permanent arming-policy rewrite.
2. Separate maintenance firmware: easier runtime isolation but introduces a
   second flash/restore cycle, firmware-identity tracking, and additional
   opportunities to overwrite unrelated state.
3. Raw NVS partition image: not selected. Overwriting the shared partition
   risks unrelated settings and bypasses normal namespace-scoped persistence.

### Bounded shutdown and reservation cleanup

The current command task's cleanup retries until its socket, AP resources, and
admission guard are released. That loop can remain live indefinitely on a
persistent platform failure. The proposed maintenance worker must therefore
wait at most 2 seconds for an explicit service-exited acknowledgement; a clock
regression or invalid time also fails the wait. This is an initial software
deadline to test, not a measured radio-stop guarantee.

The USB parser only validates and submits one bounded request. It must release
its connection lock before the maintenance worker waits or accesses NVS.
Concurrent requests receive a busy status; they do not replace the pending
request or reserve additional secret buffers. A late service exit cannot revive
a timed-out request or cause its credentials to be written.

On timeout, shutdown failure, changed flight state, or failed reservation,
deny the write, wipe the pending credential buffers, and return a bounded status
without force-deleting the Wi-Fi task or clearing retained wireless ownership.
Release only a maintenance reservation acquired by this transaction, through
its checked token API. If token release fails (including clock rollback), retain
the token and cleanup context for retries; do not report recovery complete or
accept another provisioning transaction. USB read-only telemetry and bootloader
recovery remain available, although mutating USB commands can remain blocked
until cleanup succeeds or the operator explicitly reboots.

After successful commit/readback, wipe pending buffers and use the same checked
reservation cleanup. Keep radio startup inhibited for the rest of that boot.
Persistence status and cleanup/reboot-required status must be distinguishable:
a cleanup failure after commit does not mean credentials were not stored.

## Required implementation evidence

- New independent CSPRNG application root and AP password; no hardware-derived
  SSID, command-line secret arguments, console echo, or public artifact content.
- Save a private host bundle before transmission. Preserve both old and pending
  bundles during rotation; timeout means uncertain outcome, not safe to discard
  the new key or generate another one automatically.
- Fixed-size, versioned, write-only USB envelope with an explicit maintenance
  operation, no arbitrary namespace/key selection and no readback command.
- Exact parser tests for CRC, truncation, oversize, timestamps, type, instance,
  unknown operation, and reserved-ID collisions with generated UAVObjects.
- Serialized maintenance reservation that excludes admission and mutating USB
  operations. Test race orderings, in-flight settings loads, armed rejection,
  clock rollback, AP-stop failure, task-join failure, and lost responses.
- NVS set/commit followed by internal exact readback validation before success.
  Never erase the partition on failure. Treat ambiguous persistence as unknown;
  do not promise power-loss atomicity without supporting storage tests.
- Bounded status response carries no credential bytes. Wipe transient firmware
  buffers on all exits and audit parser buffers/capture paths for retention.
- Rotation leaves no old active or pending radio session. Reboot is explicit,
  not silently triggered by a response timeout. Existing USB recovery survives.
- Cross-platform private host storage tests on declared Python platforms;
  unsupported permission enforcement fails before transmitting credentials.
- Real board provisioning, reboot, authenticated connection, rotation, recovery,
  and power-interruption checks remain separate from synthetic tests.

## Next decision

Approve the recommended maintenance transaction's radio-stop-until-reboot
behavior before implementing its lifecycle interface. This is a refinement of
the already approved local USB provisioning design, not permission to activate
radio or motors during source tests.
