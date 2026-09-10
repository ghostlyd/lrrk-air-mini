# Wi-Fi startup and mapping writer audit

Scope: `cbaa7bb`, pinned NinjaPilot source, and generated target copies from the
successful `9d9b547` build. This is a source audit, not a scheduling or flight
test. It determines where the future network task may start and which mapping
writers need exclusion.

## Mapping writers

- The target's direct `ManualControlSettingsSet` is in
  `target/firmware/pios_board.c`, in the checked boot-defaults path. It runs
  after object registration/settings loading and before GCS receiver setup,
  board-services publication, and module startup.
- Other direct setters found in pinned `flight/targets/boards/simwroom` and
  `simlitewing` are not this ESP-IDF target's board source.
- UART general object writes enter the target receiver unpack wrapper; its
  in-flight count and admission/ownership guard exclude storage mutation.
- Queued System persistence loads use `UAVObjLoad`, now wrapped at execution
  time. The actual generated System source still routes single, settings and
  metadata loads through that public boundary. No settings-load bypass was
  found in the inspected target/System paths.
- `ManualControl` subscribes `configurationUpdatedCb` to mapping updates. That
  callback calls `configuration_check`; the inspected sanity-check function
  reads settings and updates alarms, not the channel mapping.
- `Receiver` reads `ManualControlSettings` each control iteration. Its settings
  callback updates local frame-type state, not channel mapping. This audit does
  not prove that every in-progress iteration uses the newest settings snapshot;
  that timing belongs in task-level integration tests.

These findings cover the inspected pinned sources. Future direct setters or
new deferred settings mutations must participate in exclusion; callback queue
submission alone is never evidence that a writer has completed.

## Startup location

`app_main` only requests System startup; it does not establish asynchronous
readiness. The repository's `prepare_scheduler.py` generates checked System
startup: selected modules start, callback scheduler starts, then
`PIOS_LiteWing_ConfirmBootReady` must succeed. The readiness check requires
board services, selected monitored tasks, a healthy IMU and non-faulted boot
alarm within its existing deadline. It does not prove complete flight readiness.

The later Wi-Fi owning-task launch should be placed in the generated System
startup after its checked readiness and successful System queue/callback
connections, not directly after `SystemModInitialize` in `app_main`. Optional
Wi-Fi configuration/setup failure must leave existing System/USB operation
running. No startup hook is added by this audit.

## RNG dependency

Pinned ESP-IDF 5.3.2 `components/esp_hw_support/include/esp_random.h` documents
the RF-enabled entropy prerequisite for `esp_random` and `esp_fill_random`.
The later owning-task adapter must not create session/challenge randomness
before AP initialization succeeds or after AP failure. Fixture counter-based
RNG remains test-only; never reuse it in the firmware task.
