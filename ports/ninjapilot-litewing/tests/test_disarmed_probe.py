import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulation"))
from probe_contract import Evidence, ProbeFailure
from disarmed_probe import GuardedTransport, owned_loopback_sockets, stop


class DisarmedProbeTests(unittest.TestCase):
    def filled(self):
        e = Evidence()
        for _ in range(100):
            e.imu((0, 0, 9.80665, 0, 0, 0), 10.0)
        for _ in range(10):
            e.observe("FlightStatus", {"Armed": "Disarmed"}, 10.0)
            e.observe("ActuatorCommand", {"Channel": [0] * 12}, 10.0)
            e.observe("AttitudeState", {"Roll": 0, "Pitch": 0, "Yaw": 0}, 10.0)
        return e

    def test_complete_fresh_disarmed_evidence_passes(self):
        self.assertEqual(self.filled().result(10.1)["status"], "PASS")

    def test_no_samples_cannot_pass(self):
        with self.assertRaises(ProbeFailure):
            Evidence().result(10.1)

    def test_stale_stream_cannot_pass(self):
        with self.assertRaises(ProbeFailure):
            self.filled().result(10.6)

    def test_missing_actuator_stream_cannot_pass(self):
        e = Evidence()
        for _ in range(100):
            e.imu((0, 0, 9.80665, 0, 0, 0), 10.0)
            e.observe("FlightStatus", {"Armed": "Disarmed"}, 10.0)
            e.observe("AttitudeState", {"Roll": 0, "Pitch": 0, "Yaw": 0}, 10.0)
        with self.assertRaises(ProbeFailure):
            e.result(10.1)

    def test_arming_and_armed_are_rejected(self):
        for armed in ("Arming", "Armed", None, 0):
            with self.subTest(armed=armed), self.assertRaises(ProbeFailure):
                self.filled().observe("FlightStatus", {"Armed": armed}, 10.0)

    def test_any_nonzero_motor_or_short_frame_is_rejected(self):
        for channels in ([0, 1, 0, 0], [0, -1, 0, 0], [0, 0, 0], [0, math.nan, 0, 0]):
            with self.subTest(channels=channels), self.assertRaises(ProbeFailure):
                self.filled().observe("ActuatorCommand", {"Channel": channels}, 10.0)

    def test_nonfinite_sensor_and_attitude_are_rejected(self):
        for value in (math.nan, math.inf):
            with self.assertRaises(ProbeFailure):
                self.filled().imu((0, 0, value, 0, 0, 0), 10.0)
            with self.assertRaises(ProbeFailure):
                self.filled().observe("AttitudeState", {"Roll": value, "Pitch": 0, "Yaw": 0}, 10.0)

    def test_bad_event_remains_a_failure_after_recovery(self):
        e = self.filled()
        try:
            e.observe("FlightStatus", {"Armed": "Armed"}, 10.0)
        except ProbeFailure:
            pass
        e.observe("FlightStatus", {"Armed": "Disarmed"}, 10.0)
        with self.assertRaises(ProbeFailure):
            e.result(10.1)

    def test_simulator_transport_blocks_control_writes(self):
        db = {name: SimpleNamespace(obj_id=i) for i, name in enumerate(("GyroSensor", "AccelSensor", "GCSTelemetryStats"), 1)}
        with patch("disarmed_probe.socket.socket") as factory:
            link = GuardedTransport(db, Mock())
            factory.return_value.bind.assert_called_once_with(("127.0.0.1", 0))
            factory.return_value.connect.assert_called_once_with(("127.0.0.1", 9000))
            for kind, obj in ((0x20, 99), (0x22, 1), (0xA0, 99)):
                data = bytes([0x3C, kind, 10, 0]) + obj.to_bytes(4, "little") + bytes(3)
                with self.assertRaises(ProbeFailure):
                    link.send(data)
            factory.return_value.send.assert_not_called()
            sensor = bytes([0x3C, 0x20, 10, 0]) + (1).to_bytes(4, "little") + bytes(3)
            link.send(sensor)
            factory.return_value.send.assert_called_once_with(sensor)

    def test_nonloopback_native_socket_is_rejected(self):
        for address in ("*:9000", "192.0.2.1:9000", "[::]:9000"):
            with patch("disarmed_probe.subprocess.run", return_value=SimpleNamespace(stdout="p123\nn" + address + "\n", returncode=0)):
                with self.assertRaises(ProbeFailure):
                    owned_loopback_sockets(123)

    def test_native_socket_ownership_is_pid_scoped(self):
        with patch("disarmed_probe.subprocess.run", return_value=SimpleNamespace(stdout="p123\nn127.0.0.1:9000\n", returncode=0)) as command:
            self.assertEqual(owned_loopback_sockets(123), ["127.0.0.1:9000"])
            args = command.call_args.args[0]
            self.assertEqual(args[args.index("-p") + 1], "123")

    def test_cleanup_targets_only_owned_process_group(self):
        proc = Mock(pid=123)
        with patch("disarmed_probe.os.killpg") as kill:
            stop(proc)
        self.assertEqual(kill.call_args.args[0], 123)
        proc.wait.assert_called_once_with(timeout=5)


if __name__ == "__main__":
    unittest.main()
