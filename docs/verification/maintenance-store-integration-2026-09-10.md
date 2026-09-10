# Worker and scoped-store integration

At `52a518a`, the maintenance fixture links the actual asynchronous worker,
receiver, arming-inhibit implementation, LWCF decoder and scoped credential store.
The worker's store call passes through existing lifecycle assertions and then
the real store; a predicted result is compared with the real result, never used
as its replacement. NVS, radio lifecycle and RTOS scheduling remain doubles.

Ten scenarios pass under ASan/UBSan: successful storage, commit uncertainty,
initialization failure before writing, armed rejection, retained wireless owner,
admission reservation, fresh input, stop timeout, clock rollback and delayed
receiver cleanup. Assertions verify exact NVS bytes, single set/commit, expected
readback counts, balanced handles and arming inhibition during NVS operations.
A mutation that bypasses the real store fails the NVS-set assertion.

Independent review accepted this fixture with two coverage improvements. Both
were implemented: live-handle tracking rejects duplicate closes/use-after-close
and enforces the read-only reopen, and two added scenarios propagate readback
failure or mismatch after successful commit as uncertainty. The resulting twelve
scenarios pass under the same sanitizers. FlightStatus/object-manager behavior
remains mocked here; actual generated setter enforcement is tested separately.

Python produces validated submission payloads for success, uncertain, not-written
and armed cases. The C worker consumes the 152-byte payload and emits its actual
24-byte final status; Python checks transaction correlation and result using the
real wire codec. This crosses the host/worker data boundary but deliberately does
not claim to exercise the firmware UAVTalk parser: Python strips/constructs the
envelope at this boundary. The real parser has its separate interoperability
suite. The host CLI-to-driver integration also remains a separate test.

No physical flash, serial port, radio or motor operation occurred. These results
do not prove NVS power-loss behavior, activation, hardware timing or flight
readiness. Combined parser/worker/store execution and physical acceptance remain.
