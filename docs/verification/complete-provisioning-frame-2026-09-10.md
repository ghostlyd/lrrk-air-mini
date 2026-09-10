# Complete provisioning frame integration

At `48b3fdd`, Python generates the full 163-byte credential submission. The
hash-checked generated UAVTalk parser consumes it byte by byte and submits it
to the actual worker, receiver, arming helper, decoder and scoped store.
After the worker finishes, an actual status request is parsed. Python receives
the C parser's 11-byte ACK and 35-byte status frame and validates both through
the host wire codec; no response envelope is reconstructed in Python.

Six scenarios passed under ASan/UBSan: successful readback, commit failure,
failure before writing, armed rejection, readback failure and readback mismatch.
Every accepted frame gets only the queue ACK; final correlated status separately
reports its outcome. Parser receive-buffer wiping and the store fixture's exact
NVS bytes, operation counts and handle lifecycle are asserted.

Independent review found no blocking issue and confirmed the full-frame claim.
All nine USB test methods passed, including this integration, the existing
worker/store scenarios, C/Python decoder interoperability, reserved-ID checks
and UART cleanup. The CI source gate now explicitly runs the new test with the
pinned source checkout supplied, avoiding its optional local-source skip.

RTOS scheduling, radio, NVS, object registry/FlightStatus storage and CRC platform
callbacks remain doubles. The included arming helper is real; generated setter
enforcement has separate tests. These fixtures do not establish concurrent task
execution, physical serial behavior, power-loss persistence or radio activation.
No physical board access occurred.

CI for the preceding pushed revision `c4fc553` completed successfully in
[run 34509634088](https://github.com/ghostlyd/lrrk-air-mini/actions/runs/34509634088).
That result includes the POSIX provisioning matrix but is not CI evidence for
the newer complete-frame test; its run must be observed after publication.
