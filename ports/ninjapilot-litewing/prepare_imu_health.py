#!/usr/bin/env python3
"""Generate and validate repository-owned IMU schema in wrapper build output."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from verify_usb_ids import DEFINITION, RESERVED, verify


def prepare(upstream, output):
    upstream, output = Path(upstream).resolve(), Path(output).resolve()
    root = Path(__file__).resolve().parent
    if output == upstream or upstream in output.parents or output in upstream.parents:
        raise ValueError("custom generation must be outside pinned upstream")
    generator = upstream / "ground/uavobjgenerator/uavobjgenerator"
    existing = upstream / "build/uavobject-synthetics/flight"
    output.mkdir(parents=True, exist_ok=True)
    # The generator also emits an aggregate initializer whose transport bound
    # only covers this one object. Never expose that directory to the compiler.
    with tempfile.TemporaryDirectory(prefix="generate-", dir=output) as staging:
        subprocess.run([str(generator), "-flight", str(root / "uavobjects"),
                        str(upstream), "LiteWingIMUHealth"], cwd=staging, check=True)
        generated = Path(staging) / "flight"
        validate(generated, existing)
        isolated = output / "object"
        isolated.mkdir(parents=True, exist_ok=True)
        for name in ("litewingimuhealth.h", "litewingimuhealth.c"):
            shutil.copyfile(generated / name, isolated / name)
    print("IMU_SCHEMA=PASS id=0xDA60A0C6 metadata=0xDA60A0C7 gcs=readonly")


def validate(generated, existing):
    verify(existing)
    verify(generated)
    header = (generated / "litewingimuhealth.h").read_text()
    source = (generated / "litewingimuhealth.c").read_text()
    ids = DEFINITION.findall(header)
    if len(ids) != 1 or int(ids[0][1], 0) != 0xDA60A0C6:
        raise ValueError("IMU schema ID changed; review pack and access boundaries")
    occupied = set(RESERVED)
    for path in existing.glob("*.h"):
        for _, raw in DEFINITION.findall(path.read_text()):
            value = int(raw.strip(), 0)
            occupied.update((value, (value + 1) & 0xffffffff))
    if not {0xDA60A0C6, 0xDA60A0C7}.isdisjoint(occupied):
        raise ValueError("IMU object or metadata ID collision")
    if "ACCESS_READONLY << UAVOBJ_GCS_ACCESS_SHIFT" not in source:
        raise ValueError("IMU generated GCS metadata must be read-only")
    if not re.search(r"LITEWINGIMUHEALTH_ISSINGLEINST\s+1", header):
        raise ValueError("IMU must remain single instance")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        prepare(args.upstream, args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")
