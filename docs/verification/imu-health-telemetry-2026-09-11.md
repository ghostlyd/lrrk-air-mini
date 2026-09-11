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
