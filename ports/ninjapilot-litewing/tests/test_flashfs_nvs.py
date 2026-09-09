"""Non-destructive settings backend behavior, including real C failure paths."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FlashfsNvsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binary = Path(cls.directory.name) / "nvs-test"
        source = os.environ.get("LRRK_NVS_TEST_SOURCE", str(ROOT / "target/pios_litewing_flashfs_nvs.c"))
        result = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-DPIOS_INCLUDE_FLASH", "-Dmalloc=litewing_test_malloc", "-I", str(ROOT / "tests/nvs_stubs"),
            "-I", str(ROOT / "target/include"), source,
            str(ROOT / "target/litewing_uavobject_delete.c"),
            str(ROOT / "tests/flashfs_nvs_test.c"), "-o", str(cls.binary)],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_case(self, case):
        result = subprocess.run([str(self.binary), case], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_automatic_partition_erase_on_full_or_new_format(self):
        for case in ("full-preserved", "new-format-preserved"):
            with self.subTest(case=case): self.run_case(case)

    def test_layout_mismatch_does_not_destroy_stored_object(self):
        self.run_case("mismatch-preserved")

    def test_save_load_round_trip_and_exact_key(self):
        self.run_case("round-trip")

    def test_read_errors_and_absence_do_not_change_destination(self):
        for case in ("read-error", "partial-read-error", "short-read", "allocation-error", "missing"):
            with self.subTest(case=case): self.run_case(case)

    def test_save_and_commit_failures_propagate(self):
        for case in ("commit-error", "write-error"):
            with self.subTest(case=case): self.run_case(case)

    def test_object_state_distinguishes_absence_from_invalid_storage(self):
        for case in ("state-missing", "state-present", "state-error", "state-mismatch"):
            with self.subTest(case=case): self.run_case(case)

    def test_provisioning_marker_requires_successful_commit(self):
        for case in ("marker-success", "marker-commit-error", "marker-write-error", "marker-read-error", "marker-invalid"):
            with self.subTest(case=case): self.run_case(case)

    def test_uavobject_delete_reports_storage_result(self):
        for case in ("delete-success", "delete-absent", "delete-erase-error", "delete-commit-error"):
            with self.subTest(case=case): self.run_case(case)
