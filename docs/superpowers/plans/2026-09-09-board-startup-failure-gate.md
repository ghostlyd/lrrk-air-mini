# Board startup failure gate implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Prevent module initialization after any reported board startup error.

**Architecture:** Keep the shared void board initializer and add a target-local
one-shot status query. Fail early, preserve fault state, and check that query in
app_main. Do not introduce a boot-success publisher.

**Tech Stack:** C11, Python unittest, pinned NinjaPilot generated UAVObjects,
ESP-IDF 5.3.2 / ESP32-S3.

**Spec:** [Design](../specs/2026-09-09-board-startup-failure-gate-design.md)

## Global Constraints

- No device I/O, flashing, arming/settings changes or paid AI calls.
- This slice must never publish BootFault OK or claim complete startup readiness.
- Preserve the original dirty checkout and both pinned upstream source trees.
- Do not treat PIOS_WDG_Init's previous-boot flags as an initialization status.

## Task 1: Execute and gate the board startup sequence

**Files:**
- Modify `ports/ninjapilot-litewing/target/firmware/pios_board.c` (sequence/status).
- Modify `ports/ninjapilot-litewing/target/firmware/pios_board.h` (query declaration).
- Modify `ports/ninjapilot-litewing/target/firmware/litewing.c` (entry gate/logging).
- Create `ports/ninjapilot-litewing/tests/test_board_startup.py` (compile/scenarios).
- Create `ports/ninjapilot-litewing/tests/board_startup_test.c` (service boundaries).
- Create `ports/ninjapilot-litewing/tests/board_stubs/board_test.h` (host declarations).

**Interfaces:**
- Consumes existing `void PIOS_Board_Init(void)` and settings-recovery callbacks.
- Produces `bool PIOS_LiteWing_BoardServicesInitialized(void)`, false unless the
  one-shot synchronous sequence completed with no reported error.

- [x] Write a host test compiling unchanged production board/entry source and
  actual settings recovery. Supply generated object headers from the pinned
  flight tree, minimal hardware/RTOS/object service boundaries, and an ordered
  trace. Each failure process must assert:

  ```c
  app_main();
  CHECK(module_initializations == 0);
  CHECK(shutdown_requests == 1);
  CHECK(success_alarm_writes == 0);
  CHECK(no_service_calls_after_failure);
  ```

  Include delay, LED, monitor, callback scheduler, event dispatcher, flash,
  manager, identity get/set, required handle, settings inspect/load, alarms,
  UART/buffer/COM, GCS receiver, receiver mapping and board-adapter failures.
  Observe GPIO/alarm readiness and repeat calls. Nominal and watchdog-reset
  flags cases must still reach modules exactly once per initial app entry.
- [x] Run `LRRK_TEST_FLIGHT_ROOT=/path/to/pinned/NinjaPilot python3 -m unittest
  discover -s ports/ninjapilot-litewing/tests -p test_board_startup.py -v`.
  Confirm failures are assertions showing later services/modules ran, not a
  fixture compile error.
- [x] Implement one-shot state and checked early returns. The entry gate is:

  ```c
  PIOS_Board_Init();
  if (!PIOS_LiteWing_BoardServicesInitialized()) {
      printf("[LiteWing] board startup failed; modules not initialized\n");
      return;
  }
  MODULE_INITIALISE_ALL;
  ```

  Only set the service-completion status at the end; never clear the fault
  latch. Check identity getters/setters before proceeding. Use initialized
  flags to guard alarm/LED failure reporting. Failure requests PWM Shutdown
  and returns before the next dependent service.
- [x] Re-run focused tests. In disposable copies remove the app gate and bypass
  one board return, and verify the test rejects both mutations. Run the full
  host command `ports/ninjapilot-litewing/build.sh --host-only` with both pinned
  source paths, generated objects, SDK Python and linked-ELF test prerequisites.
- [x] Build via `idf.py -C ports/ninjapilot-litewing/esp-idf build` with IDF 5.3.2
  and the two pinned source roots. Re-run link/build-graph tests on this ELF.
- [ ] Commit exact changed source/tests/docs, request review, inspect CI on the
  exact head, then publish/merge only if accepted. Record limitations and build
  results in `docs/verification/board-startup-failure-gate-2026-09-09.md` and the
  issue 27 follow-up; keep the installed artifact unchanged.
