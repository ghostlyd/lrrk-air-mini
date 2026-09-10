#!/usr/bin/env python3
"""Generate the pinned target-only UAVTalk adaptation in the build directory.

No external checkout is modified. Hash and exact-anchor checks precede writes.
Original GPL notices are retained in the generated translation unit/header.
"""
import argparse
import hashlib
from pathlib import Path

PINS = {
    "uavtalk.c": "9cc5b2d9c97f8adcd28f523af8de88f62d967007f1cea8445f924a484a1b5505",
    "inc/uavtalk_priv.h": "3432f3123b1896e4bbbb112eb031384d33d9c737624bd17ea657c485bf6c7689",
}


def replace_exact(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError("pinned UAVTalk adaptation anchor changed")
    return text.replace(old, new)


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents:
        raise ValueError("output must be outside the source checkout subtree")
    inputs = {}
    for name, digest in PINS.items():
        data = (source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("unreviewed UAVTalk input: " + name)
        inputs[name] = data.decode("utf-8")
    code = replace_exact(inputs["uavtalk.c"], '#include "uavtalk_priv.h"',
                         '#include "uavtalk_priv.h"\n#include <esp_timer.h>\n#include "pios_litewing_gcsrcvr.h"\n#include "litewing_battery_pack.h"')
    code = replace_exact(code, "UAVObjPack(obj, instId, &connection->txBuffer[headerLength])",
        "LiteWingBatteryPack(obj, instId, &connection->txBuffer[headerLength])")
    code = replace_exact(code,
        "uint16_t instId, uint8_t *data)",
        "uint16_t instId, uint8_t *data, int64_t received_us)", 2)
    code = replace_exact(code,
        "iproc->instId, connection->rxBuffer);",
        "iproc->instId, connection->rxBuffer, iproc->rx_completed_us);")
    code = replace_exact(code, "UAVObjUnpack(obj, instId, data)",
        "PIOS_LiteWing_GCSReceiver_Unpack(obj, instId, data, received_us)", 2)
    code = replace_exact(code, "    iproc->state = UAVTALK_STATE_COMPLETE;",
        "    iproc->rx_completed_us = esp_timer_get_time();\n    iproc->state = UAVTALK_STATE_COMPLETE;")
    anchor = "static bool UAVTalkProcess_CS(UAVTalkConnectionData *connection, UAVTalkInputProcessor *iproc, uint8_t *rxbuffer, uint8_t length, uint8_t *position);"
    code = replace_exact(code, anchor, anchor + '\n#include "litewing_usb_uavtalk.inc"')
    code = replace_exact(code,
        "    return receiveObject(connection, iproc->type, iproc->objId, iproc->instId, connection->rxBuffer, iproc->rx_completed_us);",
        "    if (lw_usb_reserved(iproc->objId)) return lw_usb_receive(connection);\n"
        "    return receiveObject(connection, iproc->type, iproc->objId, iproc->instId, connection->rxBuffer, iproc->rx_completed_us);")
    code = replace_exact(code,
        "    UAVTalkInputProcessor *inIproc = &inConnection->iproc;",
        "    UAVTalkInputProcessor *inIproc = &inConnection->iproc;\n"
        "    if (lw_usb_reserved(inIproc->objId)) {\n"
        "        lw_usb_wipe_rx(inConnection);\n"
        "        inIproc->state = UAVTALK_STATE_SYNC;\n"
        "        return -1;\n    }")
    code = replace_exact(code,
        "    if (iproc->state == UAVTALK_STATE_ERROR || iproc->state == UAVTALK_STATE_COMPLETE) {\n        iproc->state = UAVTALK_STATE_SYNC;",
        "    if (iproc->state == UAVTALK_STATE_ERROR || iproc->state == UAVTALK_STATE_COMPLETE) {\n"
        "        lw_usb_wipe_rx(connection);\n        iproc->state = UAVTALK_STATE_SYNC;")
    code = replace_exact(code,
        "    connection->stats.rxBytes += processedBytes;\n    return iproc->state;",
        "    connection->stats.rxBytes += processedBytes;\n"
        "    if (iproc->state == UAVTALK_STATE_ERROR) lw_usb_wipe_rx(connection);\n"
        "    return iproc->state;")
    anchor = "static bool UAVTalkProcess_TYPE(UAVTalkConnectionData *connection, UAVTalkInputProcessor *iproc, uint8_t *rxbuffer, __attribute__((unused)) uint8_t length, uint8_t *position)\n{"
    code = replace_exact(code, anchor, anchor +
        "\n    /* SYNC may consume the final byte of this chunk. Wait for TYPE. */\n"
        "    if (length <= (*position)) return false;")
    header = replace_exact(inputs["inc/uavtalk_priv.h"], "    uint16_t rxPacketLength;",
        "    uint16_t rxPacketLength;\n    int64_t rx_completed_us; /* local CRC-complete time, never sender time */")
    # Fully validate before updating generated artifacts. Avoid touching mtime
    # on a no-op configure, so a build does not perpetually recompile itself.
    output.mkdir(parents=True, exist_ok=True)
    for name, text in (("uavtalk.c", code), ("uavtalk_priv.h", header)):
        destination = output / name
        if not destination.exists() or destination.read_text() != text:
            destination.write_text(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        prepare(args.source, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
