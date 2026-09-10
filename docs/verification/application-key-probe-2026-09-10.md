# Application-key reachability without pilot ownership

The operator-only `litewing-check-link` command loads a private pending bundle,
connects UDP to an explicitly supplied IPv4 address on port 2390, and sends one
HELLO with a fresh host nonce. It verifies the existing authenticated board
challenge and immediately retires the admission state. It never derives operator
keys, constructs CLAIM, transfers a session, or sends PILOT/STOP.

The probe has the admission core's one-second monotonic deadline, a 20 ms socket
timeout and a 64-receive work cap. Invalid/late proofs, short or failed sends and
close errors cannot report success. The command creates no socket if private
bundle validation fails. Output does not contain keys, identities or packet data.

```text
litewing-check-link --bundle EXISTING_PENDING_FILE --host EXPLICIT_IPV4
```

This requires the host to have already joined the intended network. It does not
join an AP, expose the password, reboot, reconfigure or mark a bundle active.
HELLO creates temporary challenge state on the responder; do not run the probe
concurrently with pilot admission. A successful challenge proves that the peer
at this endpoint can use the application key for a fresh reply. It is not
device/firmware attestation, AP-password proof, reboot evidence, pilot ownership,
arming or flight readiness. Possession of the root key by another peer remains
within the protocol's shared-key trust model.

At `07ac8e2`, the full host suite ran 270 tests: 261 passed and nine optional
OpenAI-extra tests skipped. Tests cover challenge-only retirement, invalid nonce,
static-clock timeout bounds, late replies, short/failed send, failed close,
private-load-before-socket ordering and a real localhost UDP exchange. The
loopback peer observed exactly one HELLO and no subsequent control messages.
Independent review accepted the initial protocol implementation at `0e17336`
and the operator command at `07ac8e2`, with no blocking findings. Additional
invalid-host and connect-failure branch tests remain useful coverage additions.

Only synthetic credentials and localhost traffic were used. No drone, physical
serial device, non-loopback endpoint or actual Wi-Fi association was accessed.
On-board provisioning, explicit restart, network association, fresh key proof,
and qualified flight acceptance remain distinct outstanding steps.
