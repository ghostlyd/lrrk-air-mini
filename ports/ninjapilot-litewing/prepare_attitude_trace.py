#!/usr/bin/env python3
"""Generate a read-only virtual-instance trace schema outside pinned sources."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from verify_usb_ids import DEFINITION, RESERVED, verify

OBJID = 0xE7AF695A

def validate(generated, others):
    verify(generated)
    header=(generated/'litewingattitudetrace.h').read_text()
    source=(generated/'litewingattitudetrace.c').read_text()
    ids=DEFINITION.findall(header)
    if len(ids)!=1 or int(ids[0][1],0)!=OBJID:
        raise ValueError('trace schema ID changed')
    for name,value in [('ISSINGLEINST',0),('ISSETTINGS',0)]:
        if not re.search(r'LITEWINGATTITUDETRACE_'+name+r'\s+'+str(value)+r'\b',header):
            raise ValueError('trace instance/settings contract changed')
    for expected in ('ACCESS_READONLY << UAVOBJ_GCS_ACCESS_SHIFT',
                     'UPDATEMODE_MANUAL << UAVOBJ_TELEMETRY_UPDATE_MODE_SHIFT',
                     'UPDATEMODE_MANUAL << UAVOBJ_GCS_TELEMETRY_UPDATE_MODE_SHIFT'):
        if expected not in source: raise ValueError('trace access/update contract changed')
    occupied=set(RESERVED)
    for directory in others:
        verify(directory)
        for path in directory.glob('*.h'):
            for _,raw in DEFINITION.findall(path.read_text()):
                value=int(raw.strip(),0)
                occupied.update((value,(value+1)&0xffffffff))
    if not {OBJID,OBJID+1}.isdisjoint(occupied):
        raise ValueError('trace object or metadata collision')

def prepare(upstream, output, custom):
    upstream,output=Path(upstream).resolve(),Path(output).resolve()
    if output==upstream or upstream in output.parents or output in upstream.parents:
        raise ValueError('trace generation must be outside pinned upstream')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as stage:
        subprocess.run([str(upstream/'ground/uavobjgenerator/uavobjgenerator'),
            '-flight',str(Path(__file__).parent/'uavobjects'),str(upstream),
            'LiteWingAttitudeTrace'],cwd=stage,check=True)
        generated=Path(stage)/'flight'
        validate(generated,[upstream/'build/uavobject-synthetics/flight',
                            *map(Path,custom)])
        (output/'object').mkdir(exist_ok=True)
        for name in ('litewingattitudetrace.c','litewingattitudetrace.h'):
            shutil.copyfile(generated/name,output/'object'/name)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--upstream',required=True); p.add_argument('--output',required=True)
    p.add_argument('--custom',action='append',default=[])
    a=p.parse_args()
    prepare(a.upstream,a.output,a.custom)
