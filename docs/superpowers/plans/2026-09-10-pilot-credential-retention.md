# Pilot Credential Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent future pilot-bearing firmware builds from enabling task-stack core dumps before implementing the approved USB credential workflow.

**Architecture:** Disable core dumps in the selected OpenPilot wrapper defaults and reject incompatible effective configurations during CMake configuration. Keep the existing partition layout, watchdogs, UART recovery and arming policy unchanged. This closes future dump creation, not physical extraction or previously persisted secrets.

**Tech Stack:** ESP-IDF 5.3.2, CMake, Python unittest, ESP32-S3.

**Spec:** `docs/verification/wifi-provisioning-boundary-2026-09-10.md`; credential retention finding in `docs/PORT_AND_DEPENDENCIES.md`. Operator approved the maintenance workflow on 2026-09-10 after its bounded cleanup refinement.

## Global Constraints

- Do not access serial, flash, credentials, radio, motors, eFuses, or old dumps in this source increment.
- Leave the original dirty checkout untouched; use the existing isolated worktree.
- Apply only to `ports/ninjapilot-litewing/esp-idf`, not the stock ESP-Drone baseline.
- Preserve partition offsets and watchdog behavior. Do not turn encryption on implicitly.
- Effective sdkconfig takes precedence over defaults: reject an old persisted configuration rather than silently rewriting it.
- The full approved workflow still requires USB parser integration, bounded maintenance ownership, scoped NVS writes, private host bundles, rotation, operator input, telemetry and hardware verification. This plan is its independently testable retention prerequisite, not the complete goal.

---

### Task 1: Enforce no task-stack dumps in the effective build

**Files:**
- Create: `ports/ninjapilot-litewing/esp-idf/pilot_secret_policy.cmake`
- Modify: `ports/ninjapilot-litewing/esp-idf/CMakeLists.txt`
- Modify: `ports/ninjapilot-litewing/esp-idf/sdkconfig.defaults`
- Create: `ports/ninjapilot-litewing/tests/test_pilot_secret_policy.py`
- Modify: `ports/ninjapilot-litewing/tests/test_esp_idf_wrapper.py`

**Interfaces:** The CMake policy consumes effective `CONFIG_ESP_COREDUMP_ENABLE_TO_NONE`, `CONFIG_ESP_COREDUMP_ENABLE_TO_FLASH`, and `CONFIG_ESP_COREDUMP_ENABLE_TO_UART` after `project(...)`. It returns normally only for explicit NONE with both output modes disabled. Failure uses a constant diagnostic without expanding paths or configuration values. No secret-handling runtime API is introduced.

- [ ] Write subprocess tests against the actual policy include, using temporary CMake scripts. Example script body:

```cmake
set(CONFIG_ESP_COREDUMP_ENABLE_TO_NONE y)
set(CONFIG_ESP_COREDUMP_ENABLE_TO_FLASH y)
include("<absolute test-resolved policy path>")
```

Assert nonzero exit and the fixed diagnostic for this contradictory state, flash alone, UART alone, and missing NONE. Assert success for explicit NONE with outputs absent or false. The test resolves the real source path rather than copying the policy implementation. Run with `python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_pilot_secret_policy.py -v`; confirm failure because the policy is absent before implementing it.

- [ ] Add a wrapper integration assertion that the policy include follows `project(lrrk_litewing_ninjapilot)`, and a defaults assertion requiring NONE and forbidding active FLASH/UART dump output. Run `test_esp_idf_wrapper.py` and record expected failures before changes.

- [ ] Implement the policy:

```cmake
if(NOT CONFIG_ESP_COREDUMP_ENABLE_TO_NONE OR
   CONFIG_ESP_COREDUMP_ENABLE_TO_FLASH OR
   CONFIG_ESP_COREDUMP_ENABLE_TO_UART)
    message(FATAL_ERROR "Pilot credentials require core dumps disabled; select CONFIG_ESP_COREDUMP_ENABLE_TO_NONE and reconfigure")
endif()
```

Include it immediately after `project(...)`. Replace enabled flash/ELF dump defaults with `CONFIG_ESP_COREDUMP_ENABLE_TO_NONE=y`; preserve all unrelated settings and the coredump partition.

- [ ] Run both focused suites. Confirm the subprocess tests fail when the guard is removed or weakened, then restore it and confirm pass. Run `git diff --check`, review only these files and commit.

### Task 2: Validate effective IDF configuration and document limits

**Files:**
- Create: `docs/verification/pilot-credential-retention-2026-09-10.md`
- Modify: `docs/PORT_AND_DEPENDENCIES.md`

**Interfaces:** Uses Task 1's policy and the existing pinned wrapper build. No new runtime interface.

- [ ] Configure a fresh out-of-source build with the pinned ESP-IDF 5.3.2 environment, verified NinjaPilot/reference paths and a temporary sdkconfig path. Keep the existing generated sdkconfig intact. Example invocation after environment activation:

```sh
idf.py -C ports/ninjapilot-litewing/esp-idf -B <fresh-build-directory> -D SDKCONFIG=<fresh-config-path> build
```

Use `mktemp -d` to obtain the actual temporary parent; do not erase or overwrite an existing build. The committed wrapper identity must match the build source.

- [ ] Inspect fresh effective sdkconfig for explicit NONE and disabled flash/UART outputs; inspect console and watchdog flags for preservation. Record actual build result and image size. Test effective-policy rejection with enabled dump output separately from merely reading defaults.

- [ ] Record that no device was flashed, existing dumps remain potentially sensitive, unencrypted NVS remains physically extractable, and no credential writer is yet implemented. Update the inventory to distinguish old dump-enabled builds from the new source policy; do not rewrite historical evidence as if the fix had always existed.

- [ ] Run focused suites and `git diff --check`, commit evidence, request independent review, and publish a PR. Merge only after review and hosted checks pass. Resume the approved USB provisioning implementation after this prerequisite; do not mark the overall goal complete.
