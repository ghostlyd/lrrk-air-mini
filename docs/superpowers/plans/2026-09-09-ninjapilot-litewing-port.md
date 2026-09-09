# NinjaPilot LiteWing Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible, source-pinned NinjaPilot/OpenPilot LiteWing target path for the ESP32-S3 LiteWing V2.6.C board without flashing hardware.

**Architecture:** Keep NinjaPilot as a pinned external flight-tree input. Record the checksum-verified OpenPilotESP32 WROOM patches as reference-only inputs because they do not apply cleanly to the selected `litewing` branch; apply only the repository-owned LiteWing target patch. The target-specific HAL supplies MPU6050 I2C, 20 kHz brushed duty output, UART/Wi-Fi telemetry, board identity, and fail-closed actuator behavior. Preserve the POSIX `simlitewing` path as the first executable regression gate.

**Tech Stack:** C/C++, NinjaPilot/PiOS, ESP-IDF for ESP32-S3, POSIX simulation, Gazebo bridge, Bash, Python/pytest for host-side verification, GitHub Actions for source and host checks.

**Spec:** `docs/superpowers/specs/2026-09-09-ninjapilot-litewing-port-design.md`

## Global Constraints

- Do not flash, erase, reset, arm, or spin the physical LiteWing.
- Keep battery disconnected and propellers removed during development and bench work.
- Fail closed on source revision mismatch, patch checksum mismatch, missing IMU, stale transport, or actuator range violations.
- Never let AI or a host process write motor outputs or bypass the flight controller.
- Preserve separate upstream attribution and license notices.
- Do not claim an ESP-IDF build or hardware behavior unless that gate actually ran and its evidence is recorded.

---

### Task 1: Add the immutable upstream manifest

**Files:**
- Create: `ports/ninjapilot-litewing/SOURCE_MANIFEST.json`
- Create: `ports/ninjapilot-litewing/README.md`
- Create: `ports/ninjapilot-litewing/LICENSES.md`
- Modify: `docs/PORT_AND_DEPENDENCIES.md`
- Test: `ports/ninjapilot-litewing/tests/test_manifest.py`

- [x] Record the NinjaPilot repository URL, `litewing` branch, commit `ac77304a58de6c8bd552f94668b46903adb71cb2`, and the reference ESP32 repository URL and commit `7233c97f844c0377930bcdf22998e289638b64c6`.
- [x] Record expected patch names, SHA-256 values, source paths, target board identity, ESP-IDF version policy, and a `hardware_validated: false` marker.
- [x] Record the exact LiteWing V2.6.C pin map and the evidence source under `hardware/LieWingV2.6.C/`.
- [x] Document which code is upstream, which code is adapted, and which files are repository-owned.
- [x] Add tests that reject missing required manifest fields, invalid commit formats, and a hardware-validation claim that is not explicitly false.
- [x] Update the dependency inventory to state that the NinjaPilot LiteWing target is selected and pinned, while the flashable ESP32-S3 target remains under construction.
- [x] Run the manifest tests and commit as `feat: establish LiteWing NinjaPilot and AI foundation` (merged in PR #4).

### Task 2: Implement reversible, fail-closed source bootstrap

**Files:**
- Create: `ports/ninjapilot-litewing/bootstrap.sh`
- Create: `ports/ninjapilot-litewing/revert.sh`
- Create: `ports/ninjapilot-litewing/verify_source.sh`
- Create: `ports/ninjapilot-litewing/tests/test_bootstrap_scripts.py`
- Modify: `ports/ninjapilot-litewing/SOURCE_MANIFEST.json`

- [x] Accept an explicit checkout directory and require it to be inside a caller-selected workspace.
- [x] Verify the checkout remote, exact commit, required source files, and patch checksums before mutation.
- [x] Verify every reference patch hash, run `git apply --check` for each `apply: true` patch before applying it, then record the resulting source commit and applied-patch hashes in a local marker outside the repository.
- [x] Make the operation idempotent: a matching marker is a no-op, while a mismatched marker stops with an actionable error.
- [x] Provide `revert.sh` that removes only the patches applied by this workflow and refuses to operate when the marker or source revision is ambiguous.
- [x] Ensure scripts never call `idf.py flash`, `esptool`, or any actuator command.
- [x] Test shell syntax, wrong-revision rejection, missing-patch rejection, checksum rejection, and idempotent re-run using temporary Git repositories.
- [x] Commit as `feat: establish LiteWing NinjaPilot and AI foundation` (merged in PR #4).

### Task 3: Create the repository-owned LiteWing target patch and simulator regression

**Files:**
- Create: `ports/ninjapilot-litewing/patches/litewing-target.patch`
- Create: `ports/ninjapilot-litewing/tests/test_litewing_target_contract.py`
- Modify: `ports/ninjapilot-litewing/README.md`
- Modify: `ports/ninjapilot-litewing/SOURCE_MANIFEST.json`

- [x] Add only guarded target definitions for board type `0x13`, revision `0x02`, ESP32-S3, Quad-X provisional geometry, and the V2.6.C peripheral map.
- [x] Add the platform-neutral LiteWing contract test for four channels, zeroing, saturation, IMU identity, and arming prerequisites; the upstream POSIX control regression remains open.
- [x] Add a simulator command that builds/runs the POSIX target when the pinned checkout and required host tools are present, and reports `unavailable` with the missing dependency when they are not.
- [x] Do not add optional ToF, optical-flow, barometer, or magnetometer initialization to the first target image.
- [x] Document that the schematic does not prove motor-corner order and that human bench verification is required.
- [x] Commit as `feat: establish LiteWing NinjaPilot and AI foundation` (merged in PR #4).

### Task 4: Add the MPU6050-over-I2C sensor path

**Files:**
- Create or modify: `ports/ninjapilot-litewing/patches/litewing-target.patch`
- Create: `ports/ninjapilot-litewing/tests/test_mpu6050_contract.py`
- Modify: `ports/ninjapilot-litewing/README.md`

- [x] Implement the target transport on I2C0 with SDA GPIO11, SCL GPIO10, and data-ready GPIO12.
- [x] Probe the configured MPU6050 address and `WHO_AM_I` before publishing samples.
- [x] Configure explicit sample rate, digital low-pass filter, accelerometer range, and gyro range, then publish the existing flight-tree sensor record format.
- [x] Reject missing, invalid, or stale sensor data and keep arming disabled on the fault path.
- [x] Add host tests for address probing, identity mismatch, short reads, stale data, and valid sample conversion.
- [x] Record the selected sensor-path revision semantics for board revision `0x02`.
- [x] Commit as `feat: add LiteWing MPU6050 and brushed HAL` (combined sensor/output adapter slice).

### Task 5: Add the brushed motor duty backend

**Files:**
- Create or modify: `ports/ninjapilot-litewing/patches/litewing-target.patch`
- Create: `ports/ninjapilot-litewing/tests/test_brushed_output_contract.py`
- Modify: `ports/ninjapilot-litewing/README.md`

- [x] Implement four ESP32-S3 PWM channels on GPIO5, GPIO6, GPIO3, and GPIO4 with a deterministic 20 kHz carrier.
- [x] Map the shared actuator range `0..1000` to duty, clamp before hardware writes, and stage all four channels as one validated frame before the LEDC updates.
- [x] Force all outputs to zero on initialization, disarm, failsafe, sensor fault, stale telemetry/transport, and target shutdown.
- [x] Do not expose ESC calibration or servo-pulse assumptions in the LiteWing backend.
- [x] Add host tests that prove clamping, zeroing, frame atomicity, and no output on fault.
- [x] Commit as `feat: add LiteWing MPU6050 and brushed HAL` (combined sensor/output adapter slice).

### Task 6: Add build gates and bench evidence templates

**Files:**
- Create: `ports/ninjapilot-litewing/build.sh`
- Create: `ports/ninjapilot-litewing/tests/test_build_script.py`
- Create: `docs/verification/litewing-bench-gates.md`
- Modify: `.github/workflows/ci.yml` or create the smallest appropriate workflow

- [ ] Make `build.sh` validate the manifest, build the POSIX simulator, and then invoke an ESP-IDF build only when the exact toolchain is installed.
- [x] Return a distinct unavailable result for missing ESP-IDF rather than a false pass.
- [x] Add CI for JSON/shell/host tests and source-integrity checks without requiring hardware or secrets.
- [x] Add a bench checklist covering USB identity, IMU `WHO_AM_I`, watchdog, zero output, disarm/failsafe, and physical motor/IMU orientation.
- [x] Record current toolchain availability as evidence; the current workstation lacks `idf.py`, so no ESP32 build claim is allowed until that changes.
- [x] Commit as `feat: establish LiteWing NinjaPilot and AI foundation` (merged in PR #4).

### Task 7: Review and integration gate

- [ ] Run the complete host test suite, shell checks, manifest verification, and any available simulator build.
- [ ] Review the patch for license boundaries, network fetches, secret handling, and accidental hardware mutation.
- [ ] Open a focused pull request from the feature branch; include the exact test results and explicitly list unavailable ESP-IDF/hardware gates.
- [ ] Merge only after the required checks are green and the PR description contains no unsupported hardware claim.
- [ ] Tag the merged source state only after source integrity and host gates are independently verified.
