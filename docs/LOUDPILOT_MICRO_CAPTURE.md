# LoudPilot Codex Micro capture

This is the operator workflow for configuring the Codex Micro in LoudPilot.
It applies to the current manufacturer LiteWing firmware and does not reflash
the board.

## Safety and scope

1. Keep the LiteWing secured on the bench. Keep propellers removed during
   controller configuration.
2. Connect the Codex Micro over USB-C. LoudPilot may enumerate other HID
   devices for diagnostics, but only the positively identified Micro is an
   eligible controller.
3. Connect the Mac to the LiteWing Wi-Fi network. USB-C is the controller
   input path; the Mac Wi-Fi path is the telemetry path. LoudPilot reports
   those paths separately and does not treat Wi-Fi availability as fresh
   telemetry.
4. Confirm the top status area reads `Read-only`. Intended control values are
   displayed for evidence and are not transmitted as flight commands.
5. If macOS reports an Input Monitoring error, enable LoudPilot in System
   Settings → Privacy & Security → Input Monitoring, then press `Retry`.

## Input ownership handoff

The Physical input monitor has an `Input ownership` toggle. It is off on
launch and releases the Micro so the Codex app may reconnect. Turning it on
asks macOS for exclusive HID ownership and starts LoudPilot's read-only
capture. Turning it off closes LoudPilot's capture, clears active input state,
unschedules and closes the HID manager, and releases the device so the Codex
app can reconnect. LoudPilot does not keep a shared HID session open while the
toggle is off.

LoudPilot never falls back to a shared control session when exclusive
ownership is requested. If macOS returns `kIOReturnNotPermitted` or
`kIOReturnUnsupported`, another consumer may still own the Micro or the
current macOS HID path may not support the requested operation. Release the
other consumer and press `Retry`; LoudPilot cannot close another process's HID
session from inside this app.

## Reading the programming surface

The Codex Micro panel mirrors the physical controls as five button tiles and a
dial tile:

- Amber glow: the next physical control LoudPilot is asking you to exercise.
- Green glow and dot: a recent matching HID report was observed.
- Blue outline: the tile selected for inspection in the UI.
- Blue fill: that control already has an accepted signature.

The panel always displays the current connection, Input Monitoring state,
capture step, output boundary, latest physical event, raw-report count, raw
HID bytes, raw-report age, maximum simultaneous inputs, and intended
roll/pitch/yaw/thrust values. The intended values are not flight telemetry and
are explicitly marked `not transmitted`.

## Capture order

Follow the amber prompt. For each button:

1. Press and hold the highlighted physical button.
2. Release fully.
3. Repeat the press/hold/release cycle three times without pressing another
   control.
4. Wait for the panel to report high-confidence evidence.
5. Press `Accept & continue` only when the observed physical control matches
   the amber tile.

The order is Button 1, Button 2, Button 3, Button 4, Button 5, dial clockwise,
and dial counter-clockwise. The dial must use one consistent HID signature in
both directions; generic joystick axes are never inferred as proportional
controls.

## Evidence and failure behavior

LoudPilot requires repeated press, hold, release, and raw-report evidence for
buttons. It requires repeated signed detents for each dial direction. A
release clears the corresponding intended value, and the panel records
whether two or more physical inputs were observed together. Application focus
loss, device disconnect, and `Escape` stop clear active input state and inhibit
control; a held control must emit a fresh release before it can become active
again after any of those gates clear.

After all seven signatures are accepted, the Micro mapping remains staged for
review. The staged layout is Button 1 roll left, Button 2 roll right, Button 3
pitch forward, Button 4 pitch back, the dial normalized to yaw, and Button 5
as a latched emergency stop. Thrust remains unbound. This stage does not arm,
take off, set thrust, send manual-flight packets, or invoke the OpenAI/model
loop.

## Staged validation and outdoor gate

The dashboard keeps the outdoor phase locked until all of the following are
recorded: complete Micro capture and learned mapping, fresh battery/IMU
telemetry, human-verified IMU orientation, human-verified motor corner order,
an emergency-stop proof, and a secured-bench test pass. Only after those gates
pass can the operator record explicit outdoor approval. Missing data remains
`Unavailable`; it is never converted into a safe or valid reading.

Telemetry link loss is fail-closed: the gate is active while telemetry is
unavailable or stale and clears only on a fresh decoded sensor packet. A
healthy Wi-Fi path or a log-control acknowledgement does not clear it. The
flight-command transport is still disconnected in this read-only stage.
