"""Small JSONL helpers used by the append-only audit log."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, Iterator


_IS_WINDOWS = os.name == "nt"
_PRIVATE_MODE = 0o600


def canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _private_mode_setter():
    if _IS_WINDOWS:
        try:
            import oschmod
        except ImportError as error:
            raise OSError("the Windows audit ACL backend is unavailable") from error

        return lambda descriptor, path: oschmod.set_mode(str(path), _PRIVATE_MODE)

    descriptor_chmod = getattr(os, "fchmod", None)
    if not callable(descriptor_chmod):
        raise OSError("descriptor-based audit permissions are unavailable")
    return lambda descriptor, path: descriptor_chmod(descriptor, _PRIVATE_MODE)


def _require_regular_target(path: Path, descriptor: int) -> None:
    descriptor_info = os.fstat(descriptor)
    path_info = os.stat(path, follow_symlinks=False)
    if (
        not stat.S_ISREG(descriptor_info.st_mode)
        or not stat.S_ISREG(path_info.st_mode)
        or not os.path.samestat(descriptor_info, path_info)
    ):
        raise ValueError("audit destination must be one regular file")


def append_record(path: Path, record: Dict[str, Any]) -> None:
    set_private_mode = _private_mode_setter()

    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    descriptor = os.open(path, flags, 0o600)
    try:
        _require_regular_target(path, descriptor)
        set_private_mode(descriptor, path)
        _require_regular_target(path, descriptor)
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
