# Operator provisioning connection and CLI

The separate `litewing-provision` entrypoint now provides `create` and
`reconcile`. It is not registered as an AI tool and does not alter the existing
read-only telemetry transport's allowed writes.

`create` generates independent random transaction/root/password/SSID values,
saves the pending bundle, and only then constructs the connection. `reconcile`
loads the saved transaction and gives the connection no credential-write
permission. Both retain pending records, close before reporting success, and
print only a static outcome. There is no automatic reboot, activation, bundle
promotion, retransmission, flashing, arming or motor command.

The macOS connection checks exact CH340 VID/PID, port and operator-supplied USB
location, and requests exclusive 57600-baud access. DTR/RTS are false before
open; this is not a guarantee against OS/driver line transients. Opening must
therefore be treated as a hardware operation on a secured props-removed bench.
USB-C can power motors without a battery.

Alignment sends one nonsecret status query and consumes input one byte at a
time, bounded by two seconds and 4096 iterations. It uses the existing actual
UAVTalk synchronizer, consumes ordinary telemetry, and waits for a canonical
maintenance status response before enabling the single exact credential frame.
The alignment status may name zero or a previous transaction but is never used
as transaction success. Subsequent polling retains strict transaction matching.

Review found an initial ordering defect: returning after any valid frame left
the alignment status queued when ordinary telemetry arrived first. At `c41aa4e`
the combined host-stack test reproduced that failure and then passed after the
fix. It exercises actual private storage, serial wrapper, synchronizer, codecs,
CLI and exchange against a driver-boundary double that replies dynamically.
It asserts saved bytes before open, exact submitted bytes, closure, and exactly
three writes: alignment query, credential frame, transaction status query.

Independent review closed the ordering finding at `c41aa4e` with no new blocking
issue. All 26 provisioning tests passed locally; the full host suite ran 254
tests, with 245 passing and nine optional OpenAI-extra tests skipped.
No actual device was opened. The
remaining acceptance work includes broader driver fault coverage, combined
firmware/host execution, private bundle promotion/activation and physical tests.
Windows provisioning and Linux device opening are not implemented by this CLI.

## Operator syntax (not executed during development)

Requires the package's `uavtalk` extra and an existing owner-only, ACL-free 0700
directory outside repositories. Do not put secrets in command arguments.

```text
litewing-provision create --directory PRIVATE_DIRECTORY --device EXACT_PORT --location EXACT_USB_LOCATION
litewing-provision reconcile --bundle EXISTING_PENDING_FILE --device EXACT_PORT --location EXACT_USB_LOCATION
```

After any ambiguous create outcome, retain all bundles and use `reconcile` on
that transaction; do not run `create` as an automatic retry. Verified means the
firmware reported stored/readback and completed cleanup, not that the new radio
credentials are active or that the aircraft is flight-ready. Activation remains
a separate explicit operation. Keep the draft PR unmerged until remaining
integration acceptance is complete.
