# Explicit IMU health integration

Status: source and local build verified; deployment pending.

The versioned nine-byte `LiteWingIMUHealth` object (`0xDA60A0C6`) carries
observed sensor identity, sample age and driver health. It is read-only from
the ground station. Firmware expires samples at serialization; the host adds
receipt age and rechecks age when preflight runs. Missing support on an older
image remains unknown without preventing the existing five-object stream.
This does not change arming policy or add AI motor-control tools.

## Local evidence

- Firmware/host source: `2335bb062485e3e2ad115d8cc1aa4f633e22b033`.
- ESP-IDF 5.3.2 build succeeded; generated identity matches that commit.
- Application size: `0xd5e70` bytes; 16% of the application partition free.
- Binary SHA-256: `a63eb09f1425aa57b0a5256bb9754ea201e3d5cbebc4f9f613caa43d173decc3`.
- Full port suite with SDK, pinned crypto, generated schema and build inputs:
  416 tests passed, no skips, 163.135 seconds.
- Full assistant suite with native generated-byte interoperability and installed
  optional SDK: 375 tests passed, no skips. Expected CLI and SDK diagnostic
  output remains a review observation, not a test failure.
- Independent task reviews cleared firmware and host implementation. Regressions
  reproduce queue-delay age renewal and reset-period identity inheritance before
  their fixes, and pass afterward.

The CI addition in `992d68b` builds the pinned Qt5 generator and rejects skipped
schema/interoperability tests. Its 23-test local equivalent passed; actual
Ubuntu Actions execution is still pending.

## Deployment evidence still required

Final review and CI, application-only flash with settings/credential preservation,
installed-image identity, bounded live IMU observations, and an installed-wheel
entry-point check remain separate steps. The binary above is not claimed to be
installed. No board reset, flash or motor command occurred in these checks.

Battery compatibility, physical flight configuration and controlled flight
qualification are not established by this telemetry feature. See
[parts selection](../PARTS_SELECTION.md) for outstanding physical dependencies.

## Merged-image bench result and transport defect

PR #77 merged as `e77a676419d3fb9a5c3294f323916d5f721b2787` after 25 successful
checks. The later host compatibility fix passed 378 tests without skips. The
installed host package also handled 25 optional-object NACKs from the previous
firmware while delivering 25 snapshots in five seconds; observed status was
Disarmed and all four observed motor-command channels were zero.

The merged application built with SHA-256
`1b7dc0f25094087a84c76563f891cf27503041e445db03fe78ff9ff29aba078d` and was flashed
at `0x10000`. Readback matched the application exactly. The boot/partition area,
NVS/PHY and settings were byte-identical before and after. This proves transfer
and preservation, not successful telemetry operation.

The first normal-image collection received no bytes. A temporary UART-console
build of the same source subsequently reached module startup. An object probe
received 22 healthy IMU observations with verified identity and 1–2 ms sample
age, but larger mandatory telemetry requests were NACKed.

Root cause: the custom generator also emits `uavobjectsinit.h`. Putting that
directory first in the component include search path shadows the upstream
aggregate header. Preprocessing the actual target `uavtalk.c` compile command
confirmed `UAVOBJECTS_LARGEST` was **9**, instead of the upstream **217**. Thus
successful nine-byte IMU and eight-byte status packets did not establish that
larger existing objects could be transmitted. Standalone schema tests missed
this cross-component include-resolution defect.

Header isolation is implemented in `33fdf44`. Native regression tests confirm
that the actual adapted parser resolves the upstream aggregate bound, all 115
upstream packed layouts and the custom nine-byte layout fit, and 16- and 30-byte
objects transmit successfully. The controller reports that the normal ESP-IDF
build of `33fdf44` completed with exit 0. Verification of the actual target
compile limit and live verification remain pending. The temporary console-enabled diagnostic image is
currently installed; it is not a flight release. All raw boot/serial captures
and flash backups remain private.
