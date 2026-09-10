"""Optional pinned-source integration; required locally before bench acceptance."""
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GcsProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            raise unittest.SkipTest("pinned flight checkout not supplied")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.output = Path(cls.directory.name)
        cls.source = Path(flight) / "flight/uavtalk"
        subprocess.run([sys.executable, str(ROOT / "prepare_uavtalk.py"),
            "--source", str(cls.source), "--output", str(cls.output)], check=True)
        if os.environ.get("LRRK_TEST_LATE_TIMESTAMP_MUTANT") == "1":
            generated = cls.output / "uavtalk.c"
            code = generated.read_text()
            old = "PIOS_LiteWing_GCSReceiver_Unpack(obj, instId, data, received_us)"
            assert code.count(old) == 2
            generated.write_text(code.replace(old,
                "PIOS_LiteWing_GCSReceiver_Unpack(obj, instId, data, esp_timer_get_time())"))
        cls.binary = cls.output / "protocol-test"
        result = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-parameter", "-pthread", "-I", str(ROOT / "tests/gcs_stubs"),
            "-I", str(ROOT / "target/include"), "-I", str(cls.output),
            "-I", str(cls.source / "inc"), str(cls.output / "uavtalk.c"),
            str(ROOT / "target/pios_litewing_gcsrcvr.c"),
            str(ROOT / "tests/gcs_session_unused.c"),
            str(ROOT / "target/litewing_battery_pack.c"),
            str(ROOT / "target/litewing_battery_voltage.c"),
            str(ROOT / "target/litewing_wifi_config.c"),
            str(ROOT / "tests/gcs_protocol_test.c"), "-o", str(cls.binary)],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_case(self, case):
        result = subprocess.run([str(self.binary), case], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_parser_packet_and_ack_paths(self):
        for case in ("normal", "acked"): self.run_case(case)
    def test_provisioning_split_at_every_frame_boundary(self):
        for split in range(1,163):
            with self.subTest(split=split): self.run_case(f"provision-split-{split}")
    def test_provisioning_rejections_and_status(self):
        for case in ("status","instance","type","invalid","length","collision","crc","relay"):
            with self.subTest(case=case): self.run_case("provision-"+case)
    def test_telemetry_request_remains_available_during_wireless_ownership(self):
        self.run_case("request-wireless-owner")
    def test_connection_lock_cannot_refresh_already_parsed_input(self): self.run_case("connection-lock-delay")
    def test_lookup_lock_cannot_refresh_already_parsed_input(self): self.run_case("lookup-lock-delay")
    def test_pause_after_complete_parser_does_not_refresh(self): self.run_case("between-parse-and-receive")
    def test_bad_crc_or_length_never_supplies_input(self):
        for case in ("bad-crc", "bad-length"): self.run_case(case)
    def test_failed_storage_never_supplies_input(self): self.run_case("failed-unpack")

    def test_battery_request_checks_age_at_serialization(self):
        for case in ("request-fresh", "request-stale", "request-other", "request-boundary",
                     "request-invalid", "request-future", "request-uninitialized"):
            with self.subTest(case=case): self.run_case(case)

    def test_unreviewed_source_fails_without_overwriting_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "inc").mkdir(parents=True)
            shutil.copyfile(self.source / "uavtalk.c", source / "uavtalk.c")
            shutil.copyfile(self.source / "inc/uavtalk_priv.h", source / "inc/uavtalk_priv.h")
            with (source / "uavtalk.c").open("a") as stream: stream.write("\n")
            output = root / "output"
            output.mkdir()
            (output / "uavtalk.c").write_text("preserve this output")
            result = subprocess.run([sys.executable, str(ROOT / "prepare_uavtalk.py"),
                "--source", str(source), "--output", str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((output / "uavtalk.c").read_text(), "preserve this output")
            self.assertFalse((output / "uavtalk_priv.h").exists())
