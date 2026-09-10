"""POSIX private pending bundles, outside Git; no transport or AI-tool entry.

Requires an existing owner-only directory. Windows provisioning is unavailable
until an equivalent handle/ACL/durability backend exists (other host features
remain portable). Same-user/root attackers and plaintext filesystem backups are
outside this protection. Failed saves preserve any created file for recovery,
but must never be treated as permission to transmit.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
import sys
import ctypes
import errno

from .usb_provisioning_wire import submission, ProvisioningWireError, ProvisioningStatus

MAGIC = b'LWPEND01'
SIZE = 192  # magic + transaction + LWCF + SHA256 corruption check


class BundleError(ValueError):
    """Static messages intentionally exclude credentials, paths and OS details."""


def _no_acl(fd):
    if sys.platform == 'darwin':
        # Darwin Libc acl_file.c/filesec.c: NULL + ENOENT means no ACL
        # property on an already opened descriptor. Reject any present ACL.
        libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        libc.acl_get_fd_np.argtypes = [ctypes.c_int, ctypes.c_int]
        libc.acl_get_fd_np.restype = ctypes.c_void_p
        libc.acl_free.argtypes = [ctypes.c_void_p]
        ctypes.set_errno(0)
        acl = libc.acl_get_fd_np(fd, 0x100)
        if not acl:
            if ctypes.get_errno() == errno.ENOENT:
                return
            raise BundleError('cannot verify private bundle ACL')
        try:
            raise BundleError('bundle storage ACL must be absent')
        finally:
            libc.acl_free(acl)
    elif sys.platform.startswith('linux'):
        if any(name.startswith('system.posix_acl_') for name in os.listxattr(fd)):
            raise BundleError('bundle storage ACL must be empty')
    else:
        raise BundleError('private provisioning ACL backend unavailable')


def _private(info, directory=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or (not directory and info.st_nlink != 1)):
        raise BundleError('bundle storage must be private and unaliased')


@contextmanager
def _directory(path):
    if os.name != 'posix':
        raise BundleError('private provisioning backend unavailable on this platform')
    descriptor = None
    try:
        path = Path(path).absolute()
        if path.is_symlink():
            raise BundleError('bundle directory must not be a symlink')
        resolved = path.resolve(strict=True)
        if any(os.path.lexists(parent / '.git') for parent in (resolved, *resolved.parents)):
            raise BundleError('bundle storage must be outside repositories')
        descriptor = os.open(resolved, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        _private(os.fstat(descriptor), directory=True)
        _no_acl(descriptor)
        yield resolved, descriptor
    except (OSError, ProvisioningWireError):
        raise BundleError('private bundle operation failed; preserve pending records') from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                # Never retry a possibly closed descriptor number.
                raise BundleError('private bundle close failed; preserve pending records') from None


def _record(transaction, blob):
    submission(transaction, blob)  # reuse exact firmware-compatible validation
    body = MAGIC + transaction + blob
    return body + hashlib.sha256(body).digest()


def _read(fd):
    _private(os.fstat(fd))
    _no_acl(fd)
    data = b''
    while len(data) <= SIZE:
        chunk = os.read(fd, SIZE + 1 - len(data))
        if not chunk:
            break
        data += chunk
    if (len(data) != SIZE or data[:8] != MAGIC
            or hashlib.sha256(data[:-32]).digest() != data[-32:]):
        raise BundleError('invalid pending bundle')
    transaction, blob = data[8:24], data[24:160]
    if _record(transaction, blob) != data:
        raise BundleError('invalid pending bundle')
    return transaction, blob


def save_pending(directory: Path, transaction: bytes, blob: bytes) -> Path:
    """Return only after exclusive creation, exact readback and file/dir fsync.

    Never replaces or deletes an old bundle. SHA256 detects corruption, not an
    attacker with write access. A returned path is not proof of board storage.
    """
    return _save(directory, transaction, blob, '.pending', False)


def _save(directory, transaction, blob, suffix, allow_existing):
    try:
        record = _record(transaction, blob)
    except ProvisioningWireError:
        raise BundleError('invalid pending credentials') from None
    with _directory(directory) as (resolved, parent):
        name = transaction.hex() + suffix
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        created = True
        try:
            fd = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent)
        except FileExistsError:
            if not allow_existing:
                raise
            created = False
            fd = os.open(name, flags, dir_fd=parent)
        try:
            if created:
                os.fchmod(fd, 0o600)
            _private(os.fstat(fd))
            _no_acl(fd)
            if created:
                position = 0
                while position < len(record):
                    written = os.write(fd, record[position:])
                    if written <= 0:
                        raise BundleError('pending bundle write failed')
                    position += written
            os.fsync(fd)
            os.lseek(fd, 0, os.SEEK_SET)
            if _read(fd) != (transaction, blob):
                raise BundleError('pending bundle readback failed')
            os.fsync(parent)
        finally:
            os.close(fd)
        return resolved / name


def record_stored(path: Path, status: ProvisioningStatus) -> Path:
    """Retain an immutable .stored copy after a correlated firmware result.

    This is local workflow state, not a signed receipt or activation proof.
    The trusted caller must supply the status observed on its exclusive stream.
    Existing matching copies are checked and synced, never overwritten.
    """
    transaction, blob = load_pending(path)
    if (type(status) is not ProvisioningStatus or not status.persisted_and_finished
            or status.transaction != transaction):
        raise BundleError('matching completed storage status required')
    return _save(Path(path).parent, transaction, blob, '.stored', True)


def load_pending(path: Path) -> tuple[bytes, bytes]:
    """Load validated private bytes, not an activation or persistence receipt."""
    path = Path(path)
    with _directory(path.parent) as (_, parent):
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=parent)
        try:
            transaction, blob = _read(fd)
            if path.name != transaction.hex() + '.pending':
                raise BundleError('pending bundle name mismatch')
            return transaction, blob
        finally:
            os.close(fd)
