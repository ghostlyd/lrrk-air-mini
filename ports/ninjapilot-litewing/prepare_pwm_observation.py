#!/usr/bin/env python3
"""Generate isolated, request-driven PWM observation and reject ID collisions."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from verify_usb_ids import DEFINITION, RESERVED, verify

OBJID = 0xA6453F6E


def validate(generated, existing, custom):
    for directory in (generated, existing, custom):
        verify(directory)
    header = (generated / 'litewingpwmobservation.h').read_text()
    source = (generated / 'litewingpwmobservation.c').read_text()
    ids = DEFINITION.findall(header)
    if len(ids) != 1 or int(ids[0][1], 0) != OBJID:
        raise ValueError('PWM schema ID changed; review wire and access boundaries')
    occupied = set(RESERVED)
    for directory in (existing, custom):
        for path in directory.glob('*.h'):
            for _, raw in DEFINITION.findall(path.read_text()):
                value = int(raw.strip(), 0)
                occupied.update((value, (value + 1) & 0xffffffff))
    if not {OBJID, OBJID + 1}.isdisjoint(occupied):
        raise ValueError('PWM object or metadata ID collision')
    if 'ACCESS_READONLY << UAVOBJ_GCS_ACCESS_SHIFT' not in source:
        raise ValueError('PWM generated GCS access must be read-only')
    if not re.search(r'LITEWINGPWMOBSERVATION_ISSINGLEINST\s+1', header):
        raise ValueError('PWM must remain single instance')
    if not re.search(r'LITEWINGPWMOBSERVATION_ISSETTINGS\s+0', header):
        raise ValueError('PWM must not be settings')
    for direction in ('TELEMETRY', 'GCS_TELEMETRY'):
        if f'UPDATEMODE_MANUAL << UAVOBJ_{direction}_UPDATE_MODE_SHIFT' not in source:
            raise ValueError('PWM must remain request-driven')


def prepare(upstream, output, custom, generator=None, existing=None):
    upstream, output, custom = Path(upstream).resolve(), Path(output).resolve(), Path(custom).resolve()
    if output == upstream or upstream in output.parents or output in upstream.parents:
        raise ValueError('custom generation must be outside pinned upstream')
    output.mkdir(parents=True, exist_ok=True)
    generator = Path(generator) if generator else upstream / 'ground/uavobjgenerator/uavobjgenerator'
    existing = Path(existing) if existing else upstream / 'build/uavobject-synthetics/flight'
    with tempfile.TemporaryDirectory(prefix='generate-', dir=output) as staging:
        subprocess.run([str(generator), '-flight',
                        str(Path(__file__).resolve().parent / 'uavobjects'), str(upstream),
                        'LiteWingPWMObservation'], cwd=staging, check=True)
        generated = Path(staging) / 'flight'
        validate(generated, existing, custom)
        isolated = output / 'object'
        isolated.mkdir(parents=True, exist_ok=True)
        for name in ('litewingpwmobservation.h', 'litewingpwmobservation.c'):
            shutil.copyfile(generated / name, isolated / name)
    print(f'PWM_SCHEMA=PASS id=0x{OBJID:08X} metadata=0x{OBJID+1:08X} size=36 gcs=readonly manual')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--custom', required=True)
    args = parser.parse_args()
    try:
        prepare(args.upstream, args.output, args.custom)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
