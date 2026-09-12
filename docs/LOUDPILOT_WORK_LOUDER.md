# LoudPilot and Work Louder Input

LoudPilot supports the Codex Micro through a native macOS HID boundary. Work
Louder Input remains an optional companion for device configuration; it is not
embedded, copied, or silently launched by LoudPilot.

## Evidence and scope

- Work Louder describes Codex Micro as Bluetooth / USB-C compatible and lists
  13 mechanical switches, one touch sensor, one rotary encoder, and one planar
  joystick: <https://worklouder.cc/codex-micro>.
- Work Louder Input provides no-code remapping, multi-tap actions, and mapping
  for keys, a dial, and joystick movement: <https://worklouder.cc/input>.
- Work Louder publishes the official macOS Apple-silicon release through its
  `input-releases` repository, while the public Linux port explicitly states
  that the official app is closed source:
  <https://github.com/worklouder/input-linux>.

The supplied `input-0.18.3-arm64.dmg` was inspected read-only. It contains a
Developer ID signed and notarized `input.app` with bundle identifier
`it.focusense.input-app`. LoudPilot does not redistribute that bundle or copy
its Electron resources.

## LoudPilot integration decision

LoudPilot reuses the public device model and interaction concepts while keeping
the control plane auditable:

1. `IOHIDManager` observes the selected Micro locally; generic joystick axes
   are not promoted to proportional flight controls without report evidence.
2. The physical reference surface exposes the 15 visible positions. The
   top-left knob position represents the encoder/press location; the
   top-right position is labeled as the planar joystick; the bottom-left
   position is labeled as the touch sensor.
3. Press, hold, release, simultaneous input, and relative knob events remain
   report-driven. The UI never infers a HID signature from a keycap position.
4. 360-degree rotation is a knob-only staged assignment. The knob may instead
   be staged as vertical up/down. This assignment is UI state until a separate
   flight-controller implementation is reviewed.
5. LoudPilot's ownership toggle is the coexistence boundary. Released mode
   leaves the Micro available to Codex / Work Louder Input; exclusive mode
   claims it for LoudPilot and clears all active state on release, focus loss,
   or disconnect.
6. The emulator preview renders the LiteWing command encoding locally for
   mapping tests. It does not open a socket, USB endpoint, or motor-output
   path. Physical flight output remains behind the independent fail-closed
   gate.

## Bluetooth discovery versus HID readiness

macOS can display a nearby Codex Micro name while exposing no selectable row
or HID device. That state is only a Bluetooth advertisement; it is not proof
that the controller is paired, connected, or available for input. LoudPilot
therefore keeps the nearby item read-only and labels it `waiting for HID`.

Use the in-app `Recheck HID` action after the Micro becomes available through
macOS or Work Louder Input. Only a device returned by macOS's HID registry can
be selected, captured, or claimed by LoudPilot. The rescan does not seize a
device, read control reports, or change the current ownership mode.

For a Bluetooth-capable Micro, Work Louder's documented communication sequence
is: hold the touch sensor for three seconds until the underglow turns blue,
tap to choose BLE channel 1/2/3, and wait for the pairing indicator to become
solid. Run `Recheck HID` immediately afterward because communication mode
exits after a short idle period. The fourth tap selects wired mode; use a
data-capable USB-C cable before rechecking HID. See the manufacturer's
<https://worklouder.cc/micro-setup> guide for the device-specific procedure.

## Future adapter work

The next evidence-bound adapter can add Work Louder-style layers and multi-tap
gestures after raw report capture proves their signatures. Those features must
remain separate from the immediate stop/focus-loss path and must not weaken the
telemetry, emergency-stop, or transport gates.
