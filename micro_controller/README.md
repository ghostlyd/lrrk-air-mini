# LiteWing Micro Controller

This is the first local macOS controller stage for the LiteWing V1.2:

```text
Codex Micro over Bluetooth → macOS app → LiteWing Wi-Fi telemetry
```

The current stage is intentionally read-only. It monitors Bluetooth HID
reports and subscribes to the manufacturer firmware's CRTP log port for
battery and IMU telemetry. It has no arm, thrust, setpoint, takeoff, or manual
flight transport. OpenAI integration is not called from the pilot or stop
loop, and existing credentials are not read or changed by this target.

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
swift run --package-path micro_controller LiteWingMicroControllerTests
```

## First-use checks

1. Pair and connect the Micro over Bluetooth.
2. Launch the app and confirm its product/manufacturer metadata is shown.
3. Exercise one key/button with press, hold, and release; then exercise two
   inputs together and the dial. The raw report and classified events remain
   visible in the window.
4. Disconnect the Micro and confirm the status becomes disconnected and the
   active-input count clears. Reconnect does not restore old input state.
5. Move the app out of focus and confirm control input is inhibited and active
   inputs clear.
6. Join the LiteWing Wi-Fi network, enter its address (default
   `192.168.43.42`) and UDP port `2390`, and choose **Connect read-only**.
7. Confirm telemetry age advances, battery and IMU values are populated only
   when advertised by the live log table, and positioning remains
   **Unavailable** unless it is positively verified later.

The UI shows the intended control values, but no Micro bindings are assumed
before the real reports are inspected. Generic HID axes are displayed as raw
observations and are not treated as proportional joystick axes.
