import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SettingsRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binary = Path(cls.directory.name) / "recovery-test"
        result = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "target/include"), str(ROOT / "target/litewing_settings_recovery.c"),
            str(ROOT / "tests/settings_recovery_test.c"), "-o", str(cls.binary)],
            capture_output=True, text=True, timeout=30)
        if result.returncode: raise AssertionError(result.stderr)

    def case(self, mode, index=-1, failure=0):
        result = subprocess.run([str(self.binary), mode, str(index), str(failure)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_absent_partial_and_existing_settings_survive_reboot(self):
        for mode in ("absent", "partial", "existing", *("mask%d" % i for i in range(8))):
            with self.subTest(mode=mode): self.case(mode)

    def test_every_inspection_or_existing_load_error_blocks_before_writing(self):
        for failure in (1, 2):
            for index in range(3):
                with self.subTest(failure=failure, index=index): self.case("existing", index, failure)

    def test_failed_default_save_or_readback_cannot_commit_marker(self):
        for failure in (2, 3, 4):
            for index in range(3):
                with self.subTest(failure=failure, index=index): self.case("absent", index, failure)

    def test_marker_commit_failure_is_not_success(self):
        self.case("absent", -1, 5)

    def test_noop_successful_save_cannot_provision(self):
        self.case("absent", -1, 6)
