import os
import stat
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.audit import AuditLog, REDACTED, validate_replay  # noqa: E402
from lrrk_litewing_ai.jsonl import canonical_json  # noqa: E402


def effective_mode(path: Path) -> int:
    if os.name == "nt":
        import oschmod

        return oschmod.get_mode(str(path))
    return stat.S_IMODE(path.stat().st_mode)


def set_effective_mode(path: Path, mode: int) -> None:
    if os.name == "nt":
        import oschmod

        oschmod.set_mode(str(path), mode)
    else:
        path.chmod(mode)


class AuditTests(unittest.TestCase):
    def test_missing_windows_acl_backend_fails_before_file_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            log = AuditLog(path, "session-1")

            with (
                mock.patch("lrrk_litewing_ai.jsonl._IS_WINDOWS", True),
                mock.patch.dict(sys.modules, {"oschmod": None}),
            ):
                with self.assertRaisesRegex(OSError, "Windows audit ACL backend"):
                    log.append("snapshot_received", {"id": "one"})

            self.assertFalse(path.exists())

    def test_windows_acl_backend_replaces_missing_fchmod(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            set_mode = mock.Mock()
            backend = types.SimpleNamespace(set_mode=set_mode)
            log = AuditLog(path, "session-1")

            with (
                mock.patch("lrrk_litewing_ai.jsonl._IS_WINDOWS", True, create=True),
                mock.patch("lrrk_litewing_ai.jsonl.os.fchmod", None, create=True),
                mock.patch.dict(sys.modules, {"oschmod": backend}),
            ):
                log.append("snapshot_received", {"id": "one"})

            set_mode.assert_called_once_with(str(path), 0o600)
            self.assertEqual(len(validate_replay(path)), 1)

    def test_new_audit_log_is_private_despite_permissive_umask(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            previous_umask = os.umask(0)
            try:
                AuditLog(path, "session-1").append("snapshot_received", {"id": "one"})
            finally:
                os.umask(previous_umask)

            self.assertEqual(effective_mode(path), 0o600)

    def test_append_retightens_existing_audit_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            AuditLog(path, "session-1").append("snapshot_received", {"id": "one"})
            set_effective_mode(path, 0o644)

            AuditLog(path, "session-1").append("snapshot_received", {"id": "two"})

            self.assertEqual(effective_mode(path), 0o600)

    def test_hash_chain_and_secret_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            log = AuditLog(path, "session-1")
            fake_key = "sk-" + ("x" * 16)
            fake_bearer = "Bearer " + ("y" * 16)
            log.append(
                "proposal_created",
                {"api_key": fake_key, "note": fake_bearer},
                event_at=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
            )
            log.append("preflight_result", {"overall": "PASS"})
            records = validate_replay(path)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["payload"]["api_key"], REDACTED)
            self.assertNotIn(fake_key, path.read_text(encoding="utf-8"))
            self.assertEqual(records[1]["prev_hash"], records[0]["event_hash"])

    def test_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            log = AuditLog(path, "session-1")
            log.append("preflight_result", {"overall": "PASS"})
            path.write_text(path.read_text(encoding="utf-8").replace("PASS", "BLOCKED"), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_replay(path)

    def test_truncated_final_line_can_be_recovered_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            log = AuditLog(path, "session-1")
            log.append("snapshot_received", {"id": "one"})
            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"event_id":"truncated"')
            self.assertEqual(len(validate_replay(path, allow_truncated_final_line=True)), 1)
            with self.assertRaises(ValueError):
                validate_replay(path)

    def test_canonical_json_is_order_independent(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), canonical_json({"a": 1, "b": 2}))


if __name__ == "__main__":
    unittest.main()
