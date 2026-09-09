import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.audit import AuditLog, REDACTED, validate_replay  # noqa: E402
from lrrk_litewing_ai.jsonl import canonical_json  # noqa: E402


class AuditTests(unittest.TestCase):
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
