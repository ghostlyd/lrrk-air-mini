#!/usr/bin/env python3
"""Reject generated UAVObject IDs colliding with USB maintenance reservations.

This checks the manifest-pinned generator's literal-ID header format, not
arbitrary C expressions. Runtime lookup remains an independent safeguard.
"""
import argparse
from pathlib import Path
import re

RESERVED = frozenset((0x4C575046, 0x4C575048))
DEFINITION = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z_0-9]*_OBJID)\b(.*)$", re.MULTILINE)
LITERAL = re.compile(r"(?:0[xX][0-9a-fA-F]+|0|[1-9][0-9]*)\Z")


def verify(objects):
    directory = Path(objects).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("generated-object path is not a directory")
    count = 0
    headers = sorted(directory.glob("*.h"))
    for header in headers:
        if header.is_symlink() or not header.is_file():
            raise ValueError("generated header must be a regular, non-symlink file")
        definitions = DEFINITION.findall(header.read_text(encoding="utf-8"))
        if not definitions and header.name == "uavobjectsinit.h":
            continue
        if len(definitions) != 1:
            raise ValueError("expected one generated object ID: " + header.name)
        name, raw = definitions[0]
        raw = raw.strip()
        if not LITERAL.fullmatch(raw):
            raise ValueError("unsupported generated object ID: " + name)
        value = int(raw, 16 if raw.lower().startswith("0x") else 10)
        if value > 0xFFFFFFFF:
            raise ValueError("generated object ID exceeds 32 bits: " + name)
        # UAVObject metadata uses the adjacent ID in the pinned manager.
        if value in RESERVED or ((value + 1) & 0xFFFFFFFF) in RESERVED:
            raise ValueError("USB maintenance ID collision: " + name)
        count += 1
    if not count:
        raise ValueError("no generated object IDs were checked")
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objects", required=True)
    args = parser.parse_args()
    try:
        count = verify(args.objects)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print("USB_ID_RESERVATIONS=PASS objects=" + str(count))
