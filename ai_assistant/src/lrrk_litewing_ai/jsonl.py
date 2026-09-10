"""Small JSONL helpers used by the append-only audit log."""

from __future__ import annotations

import json
import os
import stat
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Union


_IS_WINDOWS = os.name == "nt"
_PRIVATE_MODE = 0o600
# One process-wide lock also covers path aliases and separately constructed logs.
AUDIT_LOCK = threading.RLock()


def canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


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


def _close_cleanup(descriptor: int) -> None:
    """Attempt redundant cleanup once; an error may mean it already closed.

    Retrying a descriptor number could close a different, newly opened file.
    This cleanup must not turn an already committed append into a failure.
    """
    try:
        os.close(descriptor)
    except OSError:
        pass


@contextmanager
def append_transaction(path: Path) -> Iterator[int]:
    """Hold a private descriptor and undo append bytes on any raised exception.

    The caller must append only, and validate before leaving this context.
    This is exception rollback within one process, not crash recovery.
    """
    with AUDIT_LOCK:
        set_private_mode = _private_mode_setter()
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_APPEND
        for option in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK", "O_BINARY"):
            flags |= getattr(os, option, 0)
        try:
            descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, _PRIVATE_MODE)
            created = True
        except FileExistsError:
            descriptor = os.open(path, flags)
            created = False
        original_size = None
        rollback_descriptor = None
        try:
            _require_regular_target(path, descriptor)
            original_size = os.fstat(descriptor).st_size
            rollback_descriptor = os.dup(descriptor)
            set_private_mode(descriptor, path)
            _require_regular_target(path, descriptor)
            yield descriptor
            _require_regular_target(path, descriptor)
            # Primary close is part of commit. Keep an independent reference to
            # the inode until it succeeds, even if close invalidates its fd and
            # then raises. Relinquish the number BEFORE attempting close.
            closing, descriptor = descriptor, -1
            os.close(closing)
            _require_regular_target(path, rollback_descriptor)
        except BaseException:
            # Truncate/fsync the held inode, never a newly resolved path or the
            # primary descriptor number after an ambiguous close.
            restore = rollback_descriptor if rollback_descriptor is not None else descriptor
            if original_size is not None and os.fstat(restore).st_size != original_size:
                os.ftruncate(restore, original_size)
                os.fsync(restore)
            if created:
                _require_regular_target(path, restore)
                original = os.fstat(restore)
                # Windows requires all still-owned handles closed before unlink.
                # An ambiguously closed number is never owned or retried here.
                if descriptor >= 0:
                    closing, descriptor = descriptor, -1
                    _close_cleanup(closing)
                if rollback_descriptor is not None:
                    closing, rollback_descriptor = rollback_descriptor, None
                    _close_cleanup(closing)
                current = os.stat(path, follow_symlinks=False)
                if not stat.S_ISREG(current.st_mode) or not os.path.samestat(original, current):
                    raise ValueError("audit destination changed during rollback")
                path.unlink()
            raise
        finally:
            if descriptor >= 0:
                _close_cleanup(descriptor)
            if rollback_descriptor is not None:
                _close_cleanup(rollback_descriptor)


def append_record(path: Union[Path, int], record: Dict[str, Any]) -> None:
    """Write one binary record including its commit newline, checking the count.

    AuditLog passes the descriptor held by its larger validation/rollback
    transaction. A standalone path call retains the private-file protections.
    """
    if not isinstance(path, int):
        with append_transaction(path) as descriptor:
            append_record(descriptor, record)
        return
    data = (canonical_json(record) + "\n").encode("utf-8")
    if os.write(path, data) != len(data):
        raise OSError("short audit record write")


def iter_records(
    path: Path, allow_truncated_final_line: bool = False, *, require_final_newline: bool = False,
) -> Iterator[Dict[str, Any]]:
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        if allow_truncated_final_line:
            # Ignore the uncommitted suffix before decoding, even valid JSON
            # or a partial UTF-8 character. Never modify the source file.
            data = data[:data.rfind(b"\n") + 1]
        elif require_final_newline:
            raise ValueError("unterminated JSONL final line")
    raw = data.decode("utf-8")
    lines = raw.split("\n")[:-1] if require_final_newline else raw.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            raise ValueError("blank JSONL line at %d" % (index + 1))
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError("invalid JSONL at line %d" % (index + 1))
        if not isinstance(record, dict):
            raise ValueError("JSONL record at line %d is not an object" % (index + 1))
        yield record
