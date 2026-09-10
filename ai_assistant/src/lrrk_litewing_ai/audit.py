"""Hash-chained, redacted JSONL audit events."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .jsonl import append_record, canonical_json, iter_records


REDACTED = "[REDACTED]"
SECRET_FIELD_NAMES = {"api_key", "apikey", "authorization", "password", "secret", "token", "private_key"}
SECRET_VALUE_RE = re.compile(r"(?i)(?:sk-[a-z0-9_-]{8,}|bearer\s+[a-z0-9._~+/=-]{8,})")


def redact(value: Any, field_name: Optional[str] = None) -> Any:
    if field_name and field_name.lower().replace("-", "_") in SECRET_FIELD_NAMES:
        return REDACTED
    if isinstance(value, dict):
        return {str(key): redact(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str) and SECRET_VALUE_RE.search(value):
        return SECRET_VALUE_RE.sub(REDACTED, value)
    return value


def _event_hash(event: Dict[str, Any]) -> str:
    body = dict(event)
    body.pop("event_hash", None)
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def validate_replay(path: Path, allow_truncated_final_line: bool = False) -> List[Dict[str, Any]]:
    records = list(iter_records(path, allow_truncated_final_line=allow_truncated_final_line))
    previous = ""
    seen = set()
    for index, record in enumerate(records):
        for field in ("event_id", "event_type", "event_at", "session_id", "prev_hash", "event_hash"):
            if field not in record:
                raise ValueError("audit record %d is missing %s" % (index + 1, field))
        if record["event_id"] in seen:
            raise ValueError("duplicate audit event id: %s" % record["event_id"])
        seen.add(record["event_id"])
        if record["prev_hash"] != previous:
            raise ValueError("audit hash chain broken at record %d" % (index + 1))
        expected = _event_hash(record)
        if record["event_hash"] != expected:
            raise ValueError("audit event hash mismatch at record %d" % (index + 1))
        previous = record["event_hash"]
    return records


class AuditLog:
    def __init__(self, path: Path, session_id: str):
        if not session_id or not isinstance(session_id, str):
            raise ValueError("session_id must be a non-empty string")
        self.path = Path(path)
        self.session_id = session_id
        if self.path.exists():
            records = validate_replay(self.path)
            self._previous_hash = records[-1]["event_hash"] if records else ""
        else:
            self._previous_hash = ""

    def append(
        self,
        event_type: str,
        payload: Dict[str, Any],
        source: Optional[Dict[str, Any]] = None,
        event_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if not event_type or not isinstance(event_type, str):
            raise ValueError("event_type must be a non-empty string")
        timestamp = event_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("event_at must be timezone-aware")
        # Another instance may have appended since construction or our last write.
        # Callers serialize appends; concurrent writers require external locking.
        records = validate_replay(self.path) if self.path.exists() else []
        self._previous_hash = records[-1]["event_hash"] if records else ""
        record = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "event_at": timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "session_id": self.session_id,
            "source": redact(source or {}),
            "payload": redact(payload),
            "prev_hash": self._previous_hash,
        }
        record["event_hash"] = _event_hash(record)
        append_record(self.path, record)
        self._previous_hash = record["event_hash"]
        return record
