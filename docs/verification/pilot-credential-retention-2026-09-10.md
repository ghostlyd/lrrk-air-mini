# Pilot credential crash-dump policy

Implementation revision: `6120324`. This is source/build verification only.

The selected wrapper now defaults to `CONFIG_ESP_COREDUMP_ENABLE_TO_NONE=y`.
Its CMake policy runs after IDF resolves effective configuration and rejects
missing NONE, flash output, UART output, or contradictory selections. An old
dump-enabled sdkconfig is rejected rather than silently replaced. The stock
ESP-Drone project, partition table, watchdogs and flight arming policy are
unchanged.

## Verification

- Six CMake subprocess test methods exercise the actual policy. They failed
  before implementation; after adding the guard, the existing flash-enabled
  defaults still failed until corrected. All six then passed.
- Temporarily disabling the guard produced six failing subcases. Restoring
  the committed guard returned all six methods to passing; no mutation remains.
- Five existing ESP-IDF wrapper test methods passed.
- A fresh ESP-IDF 5.3.2 build using a separate sdkconfig and build directory
  passed at `6120324`. The application is `0xd3e20` bytes, with 17% free in the
  unchanged 1 MiB app partition. Persistence-link validation passed.
- The generated configuration selects NONE, disables flash/UART core dumps,
  retains `CONFIG_ESP_CONSOLE_NONE=y`, and retains task and interrupt watchdogs
  including task watchdog panic. NVS and flash encryption remain disabled.
- A separate real IDF reconfiguration with explicitly flash-enabled input
  failed at `pilot_secret_policy.cmake`, reached through the top-level include,
  with the intended diagnostic. Thus defaults do not override an unsafe
  effective configuration unnoticed. The safe build and old generated project
  sdkconfig were not overwritten by this negative test.
- Independent source review found no Critical/Important issues. The plan's
  proposed additional source-text assertions were replaced with actual CMake
  execution and real IDF configuration tests; this tests enforcement rather
  than matching source spelling.

The build emitted pre-existing SDK/CMake deprecation and target warnings;
successful compilation is not a claim of warning-free output or flight readiness.

## Limits and next steps

No firmware was flashed and no board storage was inspected or erased. Existing
dumps and full-flash backups remain potentially secret-bearing. This policy
prevents future configured core dumps; it does not erase historical copies,
encrypt the credential NVS record, prevent physical extraction, or promise
complete elimination of secret copies from RAM. Production USB provisioning,
rotation and host private-bundle storage remain to be implemented under the
approved maintenance workflow. Radio/flight tests remain separate.
