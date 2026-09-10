"""Real audit files: committed tails, exception rollback and process ordering."""

import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.audit import AuditLog, validate_replay
from lrrk_litewing_ai.jsonl import append_record, canonical_json
from lrrk_litewing_ai import jsonl


class AuditAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.directory / "audit.jsonl"
        self.log = AuditLog(self.path, "test-session")

    def test_complete_json_without_newline_is_not_committed(self):
        self.log.append("first", {})
        first = self.path.read_bytes()
        self.log.append("second", {})
        committed = self.path.read_bytes()
        for tail in (committed[len(first):-1], b'{"event_id":', b'\xff', b' '):
            with self.subTest(tail=tail[:12]):
                self.path.write_bytes(first + tail)
                with self.assertRaises(ValueError):
                    validate_replay(self.path)
                try:
                    rows = validate_replay(self.path, allow_truncated_final_line=True)
                except ValueError as error:
                    self.fail("uncommitted tail was parsed: %s" % type(error).__name__)
                self.assertEqual([r["event_type"] for r in rows], ["first"])
                self.assertEqual(self.path.read_bytes(), first + tail)

    def test_truncated_mode_skips_only_unterminated_tail(self):
        self.path.write_bytes(b'{}')
        try:
            rows = validate_replay(self.path, allow_truncated_final_line=True)
        except ValueError:
            self.fail("complete JSON tail was validated as a committed record")
        self.assertEqual(rows, [])
        for bad in (b'{bad}\n', b'\n', b'\xff\n', b'{}\n'):
            with self.subTest(bad=bad):
                self.path.write_bytes(bad + b'{unterminated')
                with self.assertRaises(ValueError):
                    validate_replay(self.path, allow_truncated_final_line=True)

    def test_append_refuses_complete_unterminated_tail_without_mutation(self):
        self.log.append("first", {})
        before = self.path.read_bytes()[:-1]
        self.path.write_bytes(before)
        with self.assertRaises(ValueError):
            self.log.append("second", {})
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(ValueError):
            AuditLog(self.path, "another-session")

    def test_strict_replay_requires_lf_between_committed_records(self):
        self.log.append("first", {})
        self.log.append("second", {})
        committed = self.path.read_bytes()
        # A CRLF stream is valid; a bare CR cannot commit a record.
        self.path.write_bytes(committed.replace(b"\n", b"\r\n"))
        self.assertEqual(len(validate_replay(self.path)), 2)
        self.path.write_bytes(committed.replace(b"\n", b"\r", 1))
        with self.assertRaises(ValueError):
            validate_replay(self.path)

    def test_native_append_uses_one_complete_binary_write(self):
        real_write = os.write
        writes = []
        def capture_write(descriptor, data):
            writes.append(data)
            return real_write(descriptor, data)
        with patch("lrrk_litewing_ai.jsonl.os.write", new=capture_write):
            self.log.append("metadata", {"label": "caf\u00e9"})
        self.assertEqual(len(writes), 1)
        self.assertIsInstance(writes[0], bytes)
        self.assertTrue(writes[0].endswith(b"\n"))
        self.assertEqual(self.path.read_bytes(), writes[0])
        self.assertEqual(validate_replay(self.path)[0]["payload"], {"label": "caf\u00e9"})

    def test_append_rejects_symlink_and_nonregular_destination(self):
        victim = self.directory / "victim"
        victim.write_bytes(b"unchanged private data")
        try:
            self.path.symlink_to(victim)
        except OSError as error:
            self.skipTest("symlink creation unavailable: %s" % type(error).__name__)
        with self.assertRaises((ValueError, OSError)):
            self.log.append("blocked", {})
        self.assertEqual(victim.read_bytes(), b"unchanged private data")
        directory_log = AuditLog(self.directory / "nonregular", "test-session")
        directory_log.path.mkdir()
        with self.assertRaises((ValueError, OSError)):
            directory_log.append("blocked", {})
        self.assertTrue(directory_log.path.is_dir())

    def test_permission_failure_restores_existence_without_writing(self):
        for exists in (False, True):
            with self.subTest(exists=exists):
                path = self.directory / ("permission-%s.jsonl" % exists)
                log = AuditLog(path, "test-session")
                if exists:
                    log.append("first", {})
                before = path.read_bytes() if exists else None
                def refused(descriptor, destination):
                    raise OSError("synthetic permission failure")
                with patch("lrrk_litewing_ai.jsonl._private_mode_setter", return_value=refused):
                    with self.assertRaises(OSError):
                        log.append("blocked", {})
                self.assertEqual(path.read_bytes() if path.exists() else None, before)

    def test_rollback_never_unlinks_a_replacement_path(self):
        victim = self.directory / "replacement"
        victim.write_bytes(b"unchanged private data")
        probe = self.directory / "symlink-probe"
        try:
            probe.symlink_to(victim)
        except OSError as error:
            self.skipTest("symlink creation unavailable: %s" % type(error).__name__)
        original_setter = jsonl._private_mode_setter()
        for exists in (False, True):
            with self.subTest(exists=exists):
                path = self.directory / ("swap-%s.jsonl" % exists)
                displaced = self.directory / ("held-%s.jsonl" % exists)
                log = AuditLog(path, "test-session")
                if exists:
                    log.append("first", {})
                before = path.read_bytes() if exists else b""
                def swap(descriptor, destination):
                    original_setter(descriptor, destination)
                    destination.rename(displaced)
                    destination.symlink_to(victim)
                with patch("lrrk_litewing_ai.jsonl._private_mode_setter", return_value=swap):
                    with self.assertRaises((ValueError, OSError)):
                        log.append("blocked", {})
                self.assertTrue(path.is_symlink())
                self.assertEqual(victim.read_bytes(), b"unchanged private data")
                self.assertEqual(displaced.read_bytes(), before)

    def test_append_then_raise_restores_exact_prior_bytes_and_existence(self):
        for prior in ("missing", "empty", "populated"):
            for partial in (False, True):
                with self.subTest(prior=prior, partial=partial):
                    path = self.directory / (prior + str(partial) + ".jsonl")
                    log = AuditLog(path, "test-session")
                    if prior == "empty":
                        path.touch(mode=0o600)
                    elif prior == "populated":
                        log.append("first", {})
                    before = path.read_bytes() if path.exists() else None
                    def failed_append(destination, record):
                        if partial:
                            # The injection is below AuditLog, and appends only.
                            with path.open("ab", buffering=0) as handle:
                                handle.write(canonical_json(record).encode()[:17])
                        else:
                            append_record(destination, record)
                        raise OSError("synthetic storage failure")
                    with patch("lrrk_litewing_ai.audit.append_record", new=failed_append):
                        with self.assertRaises(OSError):
                            log.append("failed", {})
                    self.assertEqual(path.read_bytes() if path.exists() else None, before,
                                     "failed append changed pre-append bytes/existence")
                    log.append("recovered", {})
                    self.assertEqual([r["event_type"] for r in validate_replay(path)],
                                     ["first", "recovered"] if prior == "populated" else ["recovered"])

    def test_short_binary_write_cannot_commit_an_event(self):
        self.log.append("first", {})
        before = self.path.read_bytes()
        real_write = os.write
        def short_write(descriptor, data):
            return real_write(descriptor, data[:-1])
        with patch("lrrk_litewing_ai.jsonl.os.write", new=short_write):
            with self.assertRaises(OSError):
                self.log.append("failed", {})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(validate_replay(self.path)), 1)

    def test_post_append_validation_rejects_missing_or_corrupt_record(self):
        for outcome in ("missing", "corrupt", "duplicate"):
            with self.subTest(outcome=outcome):
                path = self.directory / (outcome + ".jsonl")
                log = AuditLog(path, "test-session")
                log.append("first", {})
                before = path.read_bytes()
                def faulty_append(destination, record):
                    if outcome == "corrupt":
                        append_record(destination, dict(record, event_hash="incorrect"))
                    elif outcome == "duplicate":
                        append_record(destination, record)
                        append_record(destination, record)
                with patch("lrrk_litewing_ai.audit.append_record", new=faulty_append):
                    with self.assertRaises(ValueError):
                        log.append("failed", {})
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(len(validate_replay(path)), 1)

    def test_two_logs_serialize_refresh_write_and_rollback(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                path = self.directory / ("concurrent-%s.jsonl" % failure)
                first, second = AuditLog(path, "one"), AuditLog(path, "two")
                entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
                def delayed_append(destination, record):
                    if record["event_type"] == "first":
                        entered.set()
                        if not release.wait(3):
                            raise TimeoutError("test release missing")
                    append_record(destination, record)
                    if record["event_type"] == "first" and failure:
                        raise OSError("synthetic storage failure")
                def second_append():
                    second_started.set()
                    return second.append("second", {})
                with patch("lrrk_litewing_ai.audit.append_record", new=delayed_append), \
                        ThreadPoolExecutor(max_workers=2) as pool:
                    one = pool.submit(first.append, "first", {})
                    try:
                        self.assertTrue(entered.wait(3))
                        two = pool.submit(second_append)
                        self.assertTrue(second_started.wait(3))
                        # A correct writer cannot finish inside another append.
                        try:
                            two.result(timeout=0.1)
                            overtook = True
                        except TimeoutError:
                            overtook = False
                    finally:
                        release.set()
                    if failure:
                        with self.assertRaises(OSError):
                            one.result(timeout=3)
                    else:
                        one.result(timeout=3)
                    two.result(timeout=3)
                self.assertFalse(overtook, "second append overtook uncommitted first append")
                self.assertEqual([r["event_type"] for r in validate_replay(path)],
                                 ["second"] if failure else ["first", "second"])


if __name__ == "__main__":
    unittest.main()
