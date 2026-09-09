"""Complete task consumers + actual generated UAVObjects; host hardware/store boundary."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ThrustControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            raise unittest.SkipTest("pinned flight checkout not supplied")
        cls.flight = Path(flight)
        synth = cls.flight / "build/uavobject-synthetics/flight"
        if not (synth / "systemsettings.c").exists():
            raise AssertionError("explicit flight checkout is missing generated UAVObjects; run make uavobjects_flight")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.output = Path(cls.directory.name)
        startup = cls.output / "startup"
        subprocess.run([sys.executable, str(ROOT / "prepare_startup.py"),
            "--source", str(cls.flight / "flight"), "--output", str(startup)], check=True)
        source = cls.flight / "flight/modules"
        if os.environ.get("LRRK_TEST_ORIGINAL_THRUST") != "1":
            subprocess.run([sys.executable, str(ROOT / "prepare_control.py"),
                "--source", str(source), "--output", str(cls.output)], check=True)
            source = cls.output
        # Optional mutation experiment in disposable generated code, never upstream.
        mutant = os.environ.get("LRRK_TEST_THRUST_MUTANT")
        if mutant:
            if source != cls.output:
                raise AssertionError("mutants require adapted temporary sources")
            resets = {
                name: "    memset(" + name + ", 0, sizeof(" + name + "));"
                for name in ("lastResult", "filterAccumulator", "lastFilteredResult")
            }
            resets["lastThrottleDesired"] = "    lastThrottleDesired = 0.0f;"
            resets["startup-failsafe"] = (
                "    // Go to the neutral (failsafe) values until an ActuatorDesired update is received\n"
                "    setFailsafe();"
            )
            resets["startup-spike"] = "        AlarmsClear(SYSTEMALARMS_ALARM_ACTUATOR);"
            old = resets[mutant]
            file = source / "actuator.c"
            code = file.read_text()
            assert code.count(old) == 1
            replacement = "    /* mutation: omitted reset */"
            if mutant == "startup-spike":
                replacement = old + "\n        if (thisSysTime == 200) PIOS_Servo_Set(0, 1);"
            file.write_text(code.replace(old, replacement))
        cls.binaries = {}
        for name in ("Receiver", "Actuator", "ActuatorStartup"):
            module_name = "Actuator" if name == "ActuatorStartup" else name
            module = source / module_name / (module_name.lower() + ".c") if source != cls.output else source / (module_name.lower() + ".c")
            binary = cls.output / name
            includes = [ROOT / "tests/thrust_stubs", ROOT / "target/include", synth,
                cls.flight / "flight/uavobjects/inc", cls.flight / "flight/libraries/inc",
                cls.flight / "flight/libraries/math", cls.flight / "flight/modules/Actuator/inc"]
            objects = "systemsettings manualcontrolsettings manualcontrolcommand flightstatus accessorydesired flighttelemetrystats receiveractivity actuatorsettings mixersettings actuatordesired actuatorcommand"
            args = ["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                "-Wno-address-of-packed-member", "-ftrivial-auto-var-init=pattern",
                '-DMODULE_SOURCE="' + str(module) + '"']
            if os.environ.get("LRRK_TEST_ORIGINAL_THRUST") == "1":
                args += ["-Wno-error=incompatible-pointer-types"]
            if name == "Receiver": args += ["-DTEST_RECEIVER"]
            if name == "ActuatorStartup":
                args += ["-DTEST_STARTUP", str(startup / "alarms.c")]
                if os.environ.get("LRRK_TEST_ALARM_MUTANT") == "1":
                    args += ["-DPIOS_ALARM_GRACETIME=0"]
                objects += " systemalarms"
            for path in includes: args += ["-I", str(path)]
            args += [str(ROOT / "tests/thrust_module_test.c")]
            args += [str(synth / (obj + ".c")) for obj in objects.split()]
            args += ["-lm", "-o", str(binary)]
            result = subprocess.run(args, capture_output=True, text=True, timeout=60)
            if result.returncode: raise AssertionError(result.stderr)
            cls.binaries[name] = binary

    def run_case(self, module, mode):
        result = subprocess.run([str(self.binaries[module]), mode], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_receiver_throttle_selects_throttle(self): self.run_case("Receiver", "0")
    def test_receiver_collective_selects_collective(self): self.run_case("Receiver", "1")
    def test_receiver_none_is_not_a_supported_flight_input(self): self.run_case("Receiver", "2")
    def test_receiver_invalid_stops_input(self): self.run_case("Receiver", "255")
    def test_receiver_failed_read_stops_input(self): self.run_case("Receiver", "failed-read")
    def test_actuator_throttle_demultiplexes_thrust(self): self.run_case("Actuator", "0")
    def test_actuator_collective_preserves_separate_throttle(self): self.run_case("Actuator", "1")
    def test_actuator_none_stops_output(self): self.run_case("Actuator", "2")
    def test_actuator_invalid_stops_output(self): self.run_case("Actuator", "255")
    def test_actuator_failed_read_stops_output(self): self.run_case("Actuator", "failed-read")

    def test_failure_after_valid_control_stops_both_consumers(self):
        for module in ("Receiver", "Actuator"):
            for case in ("late-failure", "late-invalid", "write-then-fail"):
                with self.subTest(module=module, case=case): self.run_case(module, case)

    def test_successful_reads_recover_after_fault(self):
        for module in ("Receiver", "Actuator"):
            with self.subTest(module=module): self.run_case(module, "recovery")

    def test_receiver_failed_fault_publication_latches_shutdown(self):
        self.run_case("Receiver", "failed-publication")

    def test_actuator_powered_fault_recovery_restarts_slew_from_zero(self):
        self.run_case("Actuator", "powered-recovery")

    def test_actuator_fault_recovery_clears_mixer_acceleration_history(self):
        self.run_case("Actuator", "filtered-recovery")

    def test_actuator_fault_recovery_clears_feedforward_history(self):
        self.run_case("Actuator", "feedforward-recovery")

    def test_actuator_startup_without_events_keeps_critical_and_zero(self):
        self.run_case("ActuatorStartup", "startup-absent")

    def test_actuator_startup_valid_events_recover_after_alarm_grace(self):
        self.run_case("ActuatorStartup", "startup-recovery")

    def test_actuator_event_loss_after_recovery_reasserts_critical(self):
        self.run_case("ActuatorStartup", "startup-relapse")

    def test_real_alarm_downgrade_waits_grace_but_escalation_does_not(self):
        self.run_case("ActuatorStartup", "alarm-grace")
