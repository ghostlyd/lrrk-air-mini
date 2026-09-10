# Wireless runtime controller integration (in progress)

Based on merged PR #59 (`658052b`). The new controller connects encoded session
admission/control to the real receiver ownership and publication APIs. ACCEPT is
suppressed and cleared if reservation fails. Loss of the trusted disarmed or
neutral observation during admission retires pending state. Authenticated pilot
input is committed through the atomic receiver adapter; STOP, periodic expiry,
and transport fault invalidate input while retaining the reservation. Explicit
release requires both disarmed and neutral observations.

The controller requires external serialization and trusted current observations;
these are not wire fields. Seven real crypto/session/receiver scenarios run with
fatal ASan/UBSan: publication, STOP, timeout, fault, non-neutral admission, armed
admission, and fresh USB ownership conflict. The initial missing-controller test
failed; the first implementation failed the two admission-retirement assertions;
the correction passes all 36 pilot test methods with pinned mbedTLS supplied.

This is not the complete runtime: flight/settings observation validation, the
single-owner task or mutex, periodic challenge scheduling, AP/socket lifecycle,
credential provisioning, host operator client and telemetry delivery still need
integration. No runtime caller is activated by this change. Target build and
independent review are pending. No hardware access or secret provisioning occurred.
