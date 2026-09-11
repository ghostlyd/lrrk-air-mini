# Inactive actuator-slot reporting acceptance

## Source correction

The pinned upstream actuator module scales disabled mixers to ChannelMin.
LiteWing configures brushed-duty limits for four outputs, leaving inactive
tail-slot defaults at 1000. Those tail values were correctly retained by the
generic host decoder as unexpected mapping evidence.

The target source adapter now sets the existing activity flag to zero only for
a Disabled mixer in logical slots outside `LITEWING_OUTPUT_CHANNELS`, with
ordinary PWM ChannelType and ChannelAddr outside the same four-output contract.
Existing scaling preserves zero for those slots. Active mixers, physical
remaps, other channel types, fault counters, alarms, and read-only command
overrides are unchanged. The host decoder and safety policies are unchanged.
This is command-slot reporting, not a measurement of electrical motor output.

## Source validation

- The pre-fix native regression reproduced inactive-tail values of 1000.
- All 27 focused tests passed, exercising the actual adapted producer and
  generated objects, including exclusions for each predicate.
- Full port suite: 426 tests passed, no skips, with target build and generator
  prerequisites supplied.
- Full host suite: 378 tests run, one generated-interoperability skip, no
  failures. The affected 20-test module then passed without skips with its
  generator supplied.
- Independent task and whole-branch source reviews found no blocking issues.
- Normal ESP-IDF 5.3.2 ESP32-S3 build succeeded at
  `4fb49389076b4379e4801b9d9f255babe2066d98`.

## Installed application and live acceptance

The application is 876,272 bytes, SHA-256
`47e805ad287a6fcd2a4be106bae7868036625100daa82a6cc3e0d38b4bdc91a2`.
Only the application at `0x10000` was written. Full readback matched that image;
the preceding boot/partition/NVS/PHY region and settings at `0x110000..0x118000`
were byte-for-byte unchanged. The installed wrapper identity is `4fb4938`, not
a later merge or documentation commit.

The first post-flash launcher session received zero bytes. A separate bounded
reset probe observed `SPI_FAST_FLASH_BOOT`, no download-mode indicator, no
invalid-header indicator, and no detected panic marker. A subsequent
reset-neutral installed-launcher session completed successfully. This recovery
does not establish the cause or resolution of intermittent reset behavior.

Five-second offline acceptance result:

- 23,829 captured bytes, 635 valid frames, complete final frame.
- All five mandatory object types present; zero NACKs.
- All 30 actuator observations had zero in slots 5..12 and unchanged zero
  commands for the four mapped motors, with no failed-update count.
- Every observed flight status was disarmed.
- IMU reports were healthy with verified identity and samples present;
  maximum reported sample age was 4 ms.
- CLI exit code 0. No flight-control commands or OpenAI requests were issued.

Raw boot and telemetry captures, flash backups, and audit/output logs remain
private and outside Git. The previous [USB-to-OpenAI run](current-usb-ai-checkpoint-2026-09-11.md)
was on the preceding `33fdf44` image; this new image has offline acceptance only.

## Remaining work

This resolves the inactive-slot reporting mismatch on the bench. It does not
resolve configuration-aware classification of Stabilized1, elapsed IMU advisory
freshness, required-versus-optional alarm classification, repeated cold-start
reliability, battery qualification, wireless acceptance, or physical flight.
