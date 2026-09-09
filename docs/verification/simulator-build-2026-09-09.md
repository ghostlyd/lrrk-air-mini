# Simulator build observation — 2026-09-09

Target: NinjaPilot `fw_simlitewing`, source commit
`ac77304a58de6c8bd552f94668b46903adb71cb2` with the repository LiteWing contract
patch. Host: Apple Silicon macOS, Apple Clang, Homebrew Qt 5 and binutils 2.47.

## Observed results

- Generated 115 flight UAVObjects without ID collisions.
- Native compile/link produced `build/fw_simlitewing/fw_simlitewing.elf`,
  identified by `file` as a Mach-O arm64 executable despite the `.elf` suffix.
- Initial default build failed at packaging because `objcopy` was unavailable.
- After installing Homebrew binutils, `make fw_simlitewing` completed `.bin`,
  firmware-info, and `.opfw` packaging successfully.
- A separate three-second startup probe printed `PIOS_SYS_Init`, initialized
  two UDP sockets, and continued running until the harness sent SIGTERM.
  The process exited on that signal; it was not left running.
- The probe reported attitude `ok=0 err=100` and receiver `connected=0`.
  No physics bridge or sensor feed was provided. This is startup evidence,
  not successful attitude estimation, control, or simulated flight.

The compiler emitted legacy-source and Qt/macOS SDK compatibility warnings.
Build success does not resolve those warnings or validate their runtime impact.

## Reproduction and outstanding dependencies

The port README documents Qt/binutils setup and `simulate.sh`. The script is
build-only and now explicitly reports runtime as not run.

The upstream `Gazebo.md` describes Gazebo Harmonic-era `gz sim`, DART physics,
Python `gz.transport13` / `gz.msgs10`, NumPy, and Matplotlib. Gazebo is not
installed on the inspected host. Its general walkthrough targets `simposix`,
so it cannot be used unchanged as proof for `simlitewing`. A reviewed LiteWing
world/bridge configuration and sensor, mixer, failsafe, and telemetry scenarios
are still required. The native target binds UDP ports on all interfaces;
isolate or restrict those sockets before sustained simulation use.

No serial device, physical motor, or firmware flashing was involved. The owner
has no battery yet; powered hardware gates remain pending independently of
simulation progress.
