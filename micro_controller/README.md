# LoudPilot

This is the local macOS controller for the LiteWing V1.2:

```text
Codex Micro USB-C → LoudPilot macOS app → Mac Wi-Fi → LiteWing telemetry
```

LoudPilot discovers Bluetooth peripherals in-app and monitors HID reports, but
only a positively identified Codex Micro or Work Louder Micro can enter the
controller scope. Apple Magic Keyboard and unrelated HID devices may be
visible as diagnostics but cannot be selected or mapped as pilot input.

Telemetry uses the manufacturer firmware's CRTP log port for battery and IMU
data. The separate `FlightCommandWire` encoder implements the LiteWing legacy
RPYT setpoint packet and checksum, giving the host a control-plane seam without
coupling telemetry discovery to flight commands. The app starts with output
disconnected and disarmed; no output is sent merely by discovering a device.
The link-loss failsafe starts active, clears only after decoded sensor data is
fresh, and reactivates when packets age out or the connection fails. The
flight-output transport remains disconnected in this stage, so the gate cannot
transmit even when telemetry is fresh.
OpenAI integration is not called from the pilot or stop loop, and existing
credentials are not read or changed by this target.

## Build and run

The host currently has Swift 6.3.3 through the Command Line Tools, not a full
Xcode installation. Build and stage the real `.app` with:

```sh
./script/build_and_run.sh
```

Verify the staged app without launching it:

```sh
./script/build_and_run.sh --verify
```

The repository uses a small executable test runner because the current
Command Line Tools environment does not provide the XCTest module:

```sh
swift run --package-path micro_controller LoudPilotTests
```

## First-use checks

1. Connect the Codex Micro over USB-C or Bluetooth.
2. Launch LoudPilot and choose **Discover** in the Bluetooth section when a
   wireless Micro needs to be located.
3. Confirm the Micro's product/manufacturer metadata is shown and that any
   Magic Keyboard is labeled **Out of scope**.
4. Exercise one Micro button with press, hold, and release; then exercise two
   inputs together and the dial. The raw report and classified events remain
   visible in the window.
5. Disconnect the Micro and confirm the status becomes disconnected and the
   active-input count clears. Reconnect does not restore old input state.
6. Move the app out of focus and confirm control input is inhibited and active
   inputs clear.
7. Connect the Mac to the LiteWing Wi-Fi network. USB-C carries the Micro's
   HID input to LoudPilot; the Mac's Wi-Fi carries read-only telemetry. Enter
   the LiteWing address (default
   `192.168.43.42`) and UDP port `2390`, and choose **Connect**.
8. Confirm telemetry age advances, battery and IMU values are populated only
   when advertised by the live log table, and positioning remains
   **Unavailable** unless it is positively verified later.

## Guided input capture

LoudPilot shows every detected HID device and provides a labeled press-order
diagram for the selected device. For the current Codex Micro descriptor, the
guided order is Button 1 through Button 5, dial clockwise, then dial
counter-clockwise. Each button must produce repeated press, hold, and release
evidence; each dial direction must produce repeated relative detents on the
same HID signature. The app records the raw report samples and will not accept
a generic desktop axis as a joystick mapping.

The capture stage records the Micro's physical intent and proposed control
assignments. Generic HID axes are displayed as raw observations and are not
treated as proportional joystick axes. The legacy keyboard profile is retained
only for compatibility tests; it is not reachable from LoudPilot's controller
scope. Once all seven signatures are accepted, LoudPilot stages roll/pitch
button pairs, maps the dial to normalized yaw, and assigns Button 5 to the
latched emergency stop. Thrust stays unbound until a separate validated stage.

The dashboard's staged-validation gate keeps outdoor prompting locked until
fresh battery/IMU telemetry, human orientation and motor-order evidence,
emergency-stop proof, and a secured-bench pass are recorded. Missing evidence
is shown as unavailable rather than inferred.
