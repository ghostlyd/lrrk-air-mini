# USB maintenance startup integration

At `714e00d`, the hash-checked generated System module starts the waiting USB
maintenance worker before the optional Wi-Fi command task. Both start only after
module/scheduler startup, whole-boot readiness, and the existing three successful
System connection checks. Neither optional task's creation failure terminates
System or the USB telemetry recovery path. Starting the worker alone neither
writes credentials nor arms the drone.

An allocation failure may still raise the existing out-of-memory alarm;
continuing System/USB recovery does not mean alarm-free operation.

The actual generated System/scheduler test suite passed all 24 methods. The
new launch assertions first failed in three cases before implementation. Tests
cover launch ordering, successful startup, individual USB/Wi-Fi creation failure,
and failed queue/callback gates. Task-start APIs are boundary doubles in this
suite; actual worker behavior has its separate maintenance fixture.
The three maintenance test groups also passed. Independent review found no
blocking implementation issue; simultaneous failure of both optional tasks is
correct by inspection but lacks a dedicated combined-failure test.

ESP-IDF 5.3.2 built `714e00d` successfully with core dumps disabled. Schema
reservation and persistence-link checks passed. Image size is `0xd4d80`, with
17% of the unchanged 1 MiB application partition free. The existing upstream
mbedtls CMake deprecation warning remains.

This supersedes the earlier parser report's statement that startup is unwired.
The private durable host-bundle/serial workflow and combined lifecycle acceptance
remain unfinished. No real credentials, serial access, flashing, radio activation,
arming or motor commands were used in this verification. It is not flight proof.
