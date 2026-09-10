# Checked Stabilization startup: USB installation and runtime checks

## Result and scope

The clean application built from merged source
`94f5bcc490f4c437aa7a8fb9878221cb7a728768` is now installed on the
USB-connected LiteWing. The application passed write-time verification and a
separate live flash comparison. Bootloader, partition table and persisted
settings remained unchanged. A bounded 30-second telemetry observation then
found the board running, Disarmed and producing changing filtered IMU and
attitude state.

The user confirmed all four propellers removed and the battery absent before
device access. No receiver values, settings writes, arming requests or motor
commands were sent. **Arming remains Always Disarmed.** This is USB bench
evidence, not powered-operation or flight clearance.

## Exact merged candidate

ESP-IDF 5.3.2 completed a clean 1,180-step ESP32-S3 build of the exact merge
commit. All three generated Stabilization sources compiled, the application
occupied `0x57c00` bytes and the 1 MiB application partition retained
`0xa8400` bytes (66%) free. The persistence link check passed at
`UAVObjSave=0x4200c9fc`, `UAVObjLoad=0x4200ca80` and
`UAVObjDelete=0x4200a868`.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application | 359424 | `e0dab3285561113470eb4d3e19489bb4d56a785b8be617ba856e59951e94df9f` |
| ELF | 6675504 | `e946f1a8fe8be7b69bf533a85f201e9d29d5953002c2a639d67b4872c1ba5bae` |
| Generated `stabilization.c` | 21459 | `326ba723066c0904585a42c24a8f51468cfd0da1f85853ff547a03ff1fe6eb97` |
| Generated `outerloop.c` | 19195 | `49ad62540b32c808f71bfb0be056b40a15b6e7ef0116791977a70126049fd3d7` |
| Generated `innerloop.c` | 25211 | `984ff82497e23df51a153ffd1c3cd7b5375cb46da893a918e32b5613759ff66a` |

The generated-source hashes reproduce the reviewed
[Stabilization startup lifecycle](stabilization-startup-lifecycle-2026-09-09.md)
build. The clean merge build's 22,944-byte bootloader had SHA-256
`eb6c24ca513856240683b4a5bd11dfb8bcb1eed75d8b5f2947066ec3bcb2c0b7`,
which differed from the installed bootloader baseline. It was not written. The
3,072-byte build partition table matched the installed baseline at SHA-256
`a84ab9b6709ab8803191f08586451681c906dc441870525b44da907f9c142b51`,
but it was also excluded from the write.

## Application-only installation

Immediately before writing, macOS exposed exactly one matching WCH callout
device and no process owned it. Esptool 4.12.0 identified the ESP32-S3 revision
v0.2 and matched all four live regions against their private recovery-bound
files:

| Live region | Offset | Bytes | Pre-write SHA-256 |
| --- | ---: | ---: | --- |
| Bootloader | `0x0` | 22944 | `3d2d5b1543a2a27371bbd5521a9b1d9cbb3a4404ce0387cb77f8fa8d3156a11f` |
| Partition table | `0x8000` | 3072 | `a84ab9b6709ab8803191f08586451681c906dc441870525b44da907f9c142b51` |
| Previous application | `0x10000` | 355904 | `3881b0feb5065fbe794ab4bd952bd149154da340d7edd951ed8bf4938bfba4c8` |
| Settings | `0x110000` | 32768 | `c886cec93e0b5c383e6382ef478570487dde31e6d95f02c34698a6eeca9a6f7a` |

At 115200 baud, only application offset `0x10000` was written. Esptool erased
application sectors `0x10000..0x67fff`, wrote all 359,424 candidate bytes,
verified the transfer hash and hard-reset the board. A separate `verify_flash`
invocation then matched the exact new application and independently reconfirmed
the unchanged bootloader, partition table and settings before another hard
reset.

After the runtime observation, a fresh 32 KiB settings readback again had
SHA-256
`c886cec93e0b5c383e6382ef478570487dde31e6d95f02c34698a6eeca9a6f7a`
and compared byte-for-byte equal with the pre-install copy. No whole-chip erase,
settings format, bootloader or partition rewrite, security override or eFuse
change occurred. Recovery images and raw logs remain private.

## Guarded runtime observation

The existing private USB diagnostic was tested before use. Its five outbound
allowlist tests passed: named object requests, telemetry handshake/status and
acknowledgements were accepted; control/settings writes, non-allowlisted
requests and malformed frames were rejected before an OS write. The imported
NinjaPilot codec and XML paths were unchanged at pinned revision
`ac77304a58de6c8bd552f94668b46903adb71cb2`.

At 57600 baud, the probe transmitted 119 allowed telemetry status/handshake
frames and 364 named object requests. It sent no control or settings packet,
reported no failure and released the serial port. The private capture contains
120,541 bytes at SHA-256
`b137c50d97b288d99a08a0178de1a601e588d887103b4beb68e92aa10451e589`.

Offline decoding against the same pinned definitions produced these
checksum-valid sample observations:

| Observation | Result |
| --- | --- |
| `FlightStatus` | 29 samples; every `Armed` value was `Disarmed` |
| `ActuatorCommand` | 58 samples; channels 1..4 were zero in every sample |
| Requested settings | 28 samples each of ManualControl, Actuator, Mixer, FlightMode and Hw settings; one unique raw payload per object |
| `FlightModeSettings.Arming` | `Always Disarmed` |
| `AttitudeState` | 749 finite samples with changing roll, pitch, yaw and quaternion values |
| `GyroState` | 30 finite, changing filtered samples |
| `AccelState` | 30 finite, changing filtered samples |

The first `SystemAlarms` sample reported CPUOverload and Actuator Critical; the
following 57 reported both OK. Receiver remained Warning with no receiver
input, BootFault remained Uninitialised and Stabilization remained OK in all 58
samples. This records observed sample order, not precise electrical startup
timing or complete asynchronous readiness. The offline parser can resynchronize
past malformed bytes, so these are valid sampled frames rather than a claim of
lossless UART capture.

## Repository verification

The full local host gate used the exact installed candidate's ELF, its generated
ESP-IDF build graph and both pinned upstream trees. It passed 83 assistant tests
and all 269 port tests. The macOS system Python explicitly skipped nine tests
that require the optional OpenAI Agents SDK; the pull request's separate SDK
job remains a required merge gate rather than treating those local skips as
coverage.

## Remaining gates

The installed application advances issue
[27](https://github.com/ghostlyd/lrrk-air-mini/issues/27), but the persistent
BootFault state and initial critical alarm sample prevent closing it. Issues
[19](https://github.com/ghostlyd/lrrk-air-mini/issues/19) and
[26](https://github.com/ghostlyd/lrrk-air-mini/issues/26) remain open for
measured physical cutoff and full-board storage/output-inhibit evidence.

There is still no battery. Motor-corner mapping, IMU orientation/calibration,
battery/charger/connector acceptance, powered cutoff timing, receiver hardware
behavior and flight acceptance remain separate unpassed gates. Authorization
to arm or drive outputs is not evidence that any of those gates passed.
