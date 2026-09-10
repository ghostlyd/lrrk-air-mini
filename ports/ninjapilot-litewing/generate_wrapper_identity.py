#!/usr/bin/env python3
"""Generate a fail-closed identity header for the exact wrapper commit."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def git(repository, *args):
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def render(repository):
    repository = Path(repository).resolve(strict=True)
    if not repository.is_dir():
        raise ValueError("repository must be a directory")
    top = Path(git(repository, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if top != repository:
        raise ValueError("repository must be the exact Git worktree root")
    dirty = git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        raise ValueError("wrapper worktree must be clean")
    commit = git(repository, "rev-parse", "HEAD")
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError("Git returned an invalid wrapper commit")
    marker = "LRRK" + commit[:16]
    if len(marker.encode("ascii")) != 20:
        raise ValueError("wrapper identity marker must be exactly 20 bytes")
    return (
        "#ifndef LRRK_WRAPPER_IDENTITY_H\n"
        "#define LRRK_WRAPPER_IDENTITY_H\n\n"
        f'#define LRRK_WRAPPER_COMMIT "{commit}"\n'
        f'#define LRRK_WRAPPER_IDENTITY_MARKER "{marker}"\n'
        "#define LRRK_WRAPPER_IDENTITY_MARKER_LENGTH 20u\n\n"
        "#endif /* LRRK_WRAPPER_IDENTITY_H */\n"
    ).encode("ascii")


def write_identity(repository, output):
    data = render(repository)
    output = Path(output).absolute()
    if output.is_symlink():
        raise ValueError("identity output must not be a symlink")
    if output.exists():
        stat = output.stat()
        if not output.is_file() or stat.st_nlink != 1:
            raise ValueError("identity output must be an unaliased regular file")
        if output.read_bytes() == data:
            return
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".wrapper-identity-", delete=False) as tmp:
        temporary = Path(tmp.name)
        try:
            os.fchmod(tmp.fileno(), 0o644)
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        write_identity(args.repository, args.output)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
