"""The real target driver must expire input, not renew it through cached reads."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GcsReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binary = Path(cls.directory.name) / "gcs-test"
        source = os.environ.get("LRRK_GCS_TEST_SOURCE", str(ROOT / "target/pios_litewing_gcsrcvr.c"))
        flags = ["-DLRRK_TEST_UPSTREAM"] if "LRRK_GCS_TEST_SOURCE" in os.environ else []
        result = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-function", "-pthread", *flags,
            "-I", str(ROOT / "tests/gcs_stubs"), "-I", str(ROOT / "target/include"), source,
            str(ROOT / "tests/gcs_session_unused.c"),
            str(ROOT / "tests/gcs_receiver_test.c"), "-o", str(cls.binary)],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_case(self, case):
        if "LRRK_GCS_TEST_SOURCE" in os.environ and case in (
                "wireless-excludes-usb", "wireless-cannot-steal-fresh-usb",
                "ownership-change-during-unpack"):
            self.skipTest("upstream baseline has no wireless ownership API")
        result = subprocess.run([str(self.binary), case], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_startup_without_input(self): self.run_case("startup")
    def test_cached_input_expires_at_boundary(self): self.run_case("cached-expires")
    def test_repeated_reads_do_not_renew_input(self): self.run_case("reads-do-not-renew")
    def test_non_input_events_do_not_refresh(self): self.run_case("non-input-events")
    def test_unpacked_packet_cannot_acquire_a_younger_age_after_delay(self): self.run_case("delayed-unpack")
    def test_pre_wrapper_lock_delay_cannot_rejuvenate_packet(self): self.run_case("pre-wrapper-delay")
    def test_new_packet_recovers_after_timeout(self): self.run_case("reconnect")
    def test_new_identical_packet_is_still_new_input(self): self.run_case("same-values-new-packet")
    def test_clock_does_not_wrap_at_32bit_microseconds_or_milliseconds(self): self.run_case("clock-32bit-boundaries")
    def test_backward_clock_invalidates_until_new_input(self): self.run_case("clock-backwards")
    def test_failed_unpack_never_refreshes(self): self.run_case("failed-unpack")
    def test_other_objects_and_instances_do_not_refresh(self): self.run_case("unrelated-object-instance")
    def test_old_completion_cannot_replace_newer_input(self): self.run_case("out-of-order-completion")
    def test_invalid_handles_channels_and_duplicate_initialization(self): self.run_case("handles-channels")
    def test_wireless_ownership_excludes_usb_until_disarmed_release(self): self.run_case("wireless-excludes-usb")
    def test_wireless_cannot_steal_fresh_usb_input(self): self.run_case("wireless-cannot-steal-fresh-usb")
    def test_ownership_change_during_unpack_rejects_old_publication(self): self.run_case("ownership-change-during-unpack")
