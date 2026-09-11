# Corrected-image USB-to-OpenAI checkpoint

## Installed source and acceptance

The normal application built at `33fdf44add6aa8854c140a99275c996d5db69a21`
is installed; its runtime source is included in merged `f0345a8`. It is not a
rebuild bearing the merge commit identity. Application readback and unchanged
settings/boot regions are recorded in the [IMU acceptance record](imu-health-telemetry-2026-09-11.md).
PR #78 completed 13 successful checks on its final head; the optional Mermaid
check was skipped. Earlier branch-head checks are separate runs.

The existing installed host package ran `litewing-usb-advisory` for 15 seconds
with `--live-agent --max-calls 1`, using the previously approved project key.
The key stayed in the host child environment; it was not rewritten or sent to
the board. No modem-line reset, settings write, or motor command was issued.

- Exit code 0; 74 snapshots offered and one completed application-level provider
  invocation. This is not a count of underlying model requests.
- The audit chain validated and the returned answer hash matched the provider
  result. Output retained its historical-observation label.
- Capture: 70,925 bytes, 1,888 valid frames, no NACKs, complete final frame.
- 224 IMU reports: verified identity, samples present, healthy state, maximum
  reported sample age 4 ms.
- 74 FlightStatus reports were disarmed; 89 actuator reports contained four
  zero motor commands.
- Capture, output, error log and audit were mode 0600 in an owner-only temporary
  directory. The existing secret-pattern scanner found no matches in textual
  artifacts. Raw data and response text remain private and outside Git.

This establishes working board-to-Mac-to-OpenAI advisory integration on the
corrected image, not continuous service availability or permission to fly.

## Findings that remain real integration work

The deterministic report was BLOCKED. Fresh transport and identity observations
do not imply an all-clear report:

1. The analyzed IMU observation was 45.2 ms old, exceeding the 20 ms health
   freshness rule, despite healthy fresh board reports in the capture. The
   host correctly counts elapsed time. Do not remove aging or inflate the
   threshold merely to obtain PASS. Worker scheduling and object aggregation
   must be considered separately from board sample freshness.
2. `stabilized1` is an OpenPilot configuration slot, not proof of its configured
   stabilization modes. The generic host analyzer does not currently accept it
   as an evidenced attitude/rate configuration.
3. Channels 5..12 report 1000 while the four mapped motors report zero. The host
   flags these as unmapped outputs. The pinned upstream actuator module scales
   disabled mixers to ChannelMin; determining safe target-specific treatment
   requires the four-output board contract, not silently dropping generic
   nonzero channel evidence.
4. Receiver Warning and several Uninitialised subsystem alarms are present.
   Required versus optional subsystem treatment needs target/configuration
   evidence; no blanket alarm suppression is justified by this run.
5. Reported voltage was about 4.18 V. This does not identify a fitted battery,
   establish capacity/discharge capability, or resolve connector/charging
   compatibility. The owner's arriving battery remains unqualified.

## Scope still outstanding

The [parts inventory](../PARTS_SELECTION.md) retains the battery, connector,
polarity, fit, mass and charge-current checks. Optional flow/range hardware is
not needed for the initial attitude/rate target but is not implemented as a
qualified position-hold capability. Wireless pilot/telemetry acceptance,
repeated cold-start reliability, battery-powered operation and controlled
physical flight remain separate unfinished work. Prior motor/IMU configuration
records are historical evidence, not replacements for current-image acceptance.
