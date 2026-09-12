#!/usr/bin/env python3
"""Generate object-manager write exclusion for bounded credential maintenance."""
import argparse
import hashlib
from pathlib import Path

PIN = "8a75c4b717ddaa86cab9b44304eb66f98e2e55dac81edf50fdd1e219c0f88566"


def replace_exact(code, old, new, count=1):
    if code.count(old) != count:
        raise ValueError("pinned arming-maintenance anchor changed")
    return code.replace(old, new)


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("output must be separate from source and its ancestors")
    path = (source / "uavobjectmanager.c").resolve()
    if source not in path.parents:
        raise ValueError("input escapes source subtree")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != PIN:
        raise ValueError("unreviewed object-manager input")
    code = data.decode("utf-8")
    # This upstream Unpack does not consult GCS access metadata. Enforce the
    # custom generated read-only contract at the common inbound boundary,
    # including metadata writes which could otherwise remove the restriction.
    code = replace_exact(code,
        "int32_t UAVObjUnpack(UAVObjHandle obj_handle, uint16_t instId, const uint8_t *dataIn)\n{",
        "int32_t UAVObjUnpack(UAVObjHandle obj_handle, uint16_t instId, const uint8_t *dataIn)\n{\n"
        "    if (obj_handle && (UAVObjGetID(obj_handle) == 0xDA60A0C6u ||\n"
        "                       UAVObjGetID(obj_handle) == 0xDA60A0C7u ||\n"
        "                       UAVObjGetID(obj_handle) == 0xA6453F6Eu ||\n"
        "                       UAVObjGetID(obj_handle) == 0xA6453F6Fu ||\n"
        "                       UAVObjGetID(obj_handle) == 0xE7AF695Au ||\n"
        "                       UAVObjGetID(obj_handle) == 0xE7AF695Bu)) return -1;")
    code = replace_exact(code, '#include "inc/uavobjectprivate.h"',
                         '#include "inc/uavobjectprivate.h"\n#include <stddef.h>\n'
                         '#include "flightstatus.h"\n#include "litewing_arming_maintenance.h"\n'
                         '#include "litewing_telemetry_objects.h"')
    code = replace_exact(code, "static xSemaphoreHandle mutex;",
                         'static xSemaphoreHandle mutex;\n#include "litewing_arming_maintenance.inc"')
    for anchor, size in (
        ("        memcpy(InstanceData(instEntry), dataIn, obj->instance_size);", "obj->instance_size"),
        ("        memcpy(InstanceData(instEntry) + offset, dataIn, size);", "size"),
    ):
        offset = "offset" if size == "size" else "0"
        guard = (f"        if (!lw_arming_write_allowed(obj_handle,dataIn,{offset},{size})) {{\n"
                 "            goto unlock_exit;\n        }\n")
        code = replace_exact(code, anchor, guard + anchor, 1 if size == "size" else 2)
    code += "\n" + (Path(__file__).resolve().parent /
                    "target/include/litewing_telemetry_objects.inc").read_text()
    target = output / "uavobjectmanager.c"
    if target.is_symlink() or (target.exists() and (not target.is_file() or target.stat().st_nlink != 1)):
        raise ValueError("output must be an unaliased regular file")
    output.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text() != code:
        target.write_text(code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        prepare(args.source, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
