"""Small JSONL helpers used by the append-only audit log."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, Iterator


def canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def append_record(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    descriptor = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("audit destination must be a regular file")
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(canonical_json(record))
            handle.write("\n")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def iter_records(path: Path, allow_truncated_final_line: bool = False) -> Iterator[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    has_final_newline = raw.endswith(("\n", "\r"))
    for index, line in enumerate(lines):
        if not line.strip():
            raise ValueError("blank JSONL line at %d" % (index + 1))
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            is_final = index == len(lines) - 1 and not has_final_newline
            if is_final and allow_truncated_final_line:
                return
            raise ValueError("invalid JSONL at line %d" % (index + 1))
        if not isinstance(record, dict):
            raise ValueError("JSONL record at line %d is not an object" % (index + 1))
        yield record
