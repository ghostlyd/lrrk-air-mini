#!/usr/bin/env python3
"""Generate pinned USB RX idle ticks and owned UART-buffer clearing."""
import argparse
import hashlib
from pathlib import Path

PIN="968c22a81b0f69c8d2628ba08519d77497daa2cae7575ed5a943a7f2bac4d4ff"


def replace(code,old,new):
    if code.count(old)!=1:
        raise ValueError("pinned USB telemetry anchor changed")
    return code.replace(old,new)


def prepare(source,output):
    source,output=Path(source).resolve(),Path(output).resolve()
    if source==output or source in output.parents or output in source.parents:
        raise ValueError("output must be separate from source")
    original=(source/"telemetry.c").resolve()
    if source not in original.parents:
        raise ValueError("telemetry input escapes source")
    data=original.read_bytes()
    if hashlib.sha256(data).hexdigest()!=PIN:
        raise ValueError("unreviewed telemetry input")
    code=replace(data.decode("utf-8"),'#include "telemetry.h"',
                 '#include "telemetry.h"\n#include "litewing_usb_uart.h"')
    old="""            if (bytes_to_process > 0) {
                UAVTalkProcessInputStream(uavTalkCon, serial_data, bytes_to_process);
            }
        } else {
            vTaskDelay(5);
        }"""
    new="""            /* Idle reads tick credential assembly expiry in this same task.
             * Reject impossible lengths before narrowing to the parser's u8. */
            if (bytes_to_process <= sizeof(serial_data)) {
                UAVTalkProcessInputStream(uavTalkCon, serial_data, (uint8_t)bytes_to_process);
            } else {
                UAVTalkProcessInputStream(uavTalkCon, NULL, 0);
            }
            lw_usb_uart_clear(serial_data, sizeof(serial_data));
        } else {
            UAVTalkProcessInputStream(uavTalkCon, NULL, 0);
            vTaskDelay(5);
        }"""
    code=replace(code,old,new)
    target=output/"telemetry.c"
    if target.is_symlink() or (target.exists() and (not target.is_file() or target.stat().st_nlink!=1)):
        raise ValueError("output must be an unaliased regular file")
    output.mkdir(parents=True,exist_ok=True)
    if not target.exists() or target.read_text()!=code:
        target.write_text(code)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    try:
        prepare(args.source,args.output)
    except (OSError,ValueError) as error:
        parser.exit(1,str(error)+"\n")
