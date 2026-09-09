#!/usr/bin/env python3
"""Reject firmware whose persistence API still resolves to weak no-op stubs.

Symbol linkage is necessary, not proof of NVS durability or valid settings.
This gate never opens a device or changes the inspected artifact.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys

FUNCTIONS = ("UAVObjSave", "UAVObjLoad", "UAVObjDelete")
ANCHOR = "uavobject_persistence_linked"


def verify(elf, nm):
    with Path(elf).open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ValueError("candidate is not an ELF artifact")
    result = subprocess.run([nm, "-g", "--defined-only", str(elf)],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError("nm failed to inspect the artifact")
    symbols = {}
    for line in result.stdout.splitlines():
        match = re.fullmatch(r"\s*([0-9a-fA-F]+)\s+(\S)\s+(\S+)\s*", line)
        if not match:
            continue
        address, kind, name = match.groups()
        if name in (*FUNCTIONS, ANCHOR, "UAVObjPers_stub"):
            if name in symbols:
                raise ValueError("ambiguous duplicate symbol: " + name)
            symbols[name] = (int(address, 16), kind)
    if ANCHOR not in symbols or symbols[ANCHOR][0] == 0 or symbols[ANCHOR][1] not in ("R", "D"):
        raise ValueError("real persistence linker anchor is absent")
    addresses = set()
    stub_address = symbols.get("UAVObjPers_stub", (None, None))[0]
    for name in FUNCTIONS:
        address, kind = symbols.get(name, (None, None))
        if kind != "T" or not address or address == stub_address or address in addresses:
            raise ValueError("persistence function is missing, weak or aliased: " + name)
        addresses.add(address)
    return symbols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", required=True)
    parser.add_argument("--nm", required=True)
    args = parser.parse_args()
    try:
        symbols = verify(args.elf, args.nm)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("PERSISTENCE_LINK=FAIL " + str(error), file=sys.stderr)
        return 1
    print("PERSISTENCE_LINK=PASS " + " ".join(
        "%s=0x%x" % (name, symbols[name][0]) for name in FUNCTIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
