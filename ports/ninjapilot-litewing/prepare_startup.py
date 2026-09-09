#!/usr/bin/env python3
"""Generate hash-checked LiteWing event/alarm startup error propagation.

Only build-directory copies change. Preserve upstream GPL notices and normal
alarm/dispatch behavior; validate all input bytes and anchors before writes.
"""
import argparse
import hashlib
from pathlib import Path

PINS = {
    "libraries/alarms.c": "85a4828d601673db7964dbf13600ee93687821a0818c5bd4a479f4ed42560fdd",
    "uavobjects/eventdispatcher.c": "5778e5de80793601bc53ccdecd80865eaaa38d806eb032de297576a9c6e84ddb",
}


def replace_exact(code, old, new):
    if code.count(old) != 1:
        raise ValueError("pinned startup adaptation anchor changed")
    return code.replace(old, new)


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("output must be separate from the source subtree and its ancestors")
    inputs = {}
    for name, digest in PINS.items():
        data = (source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("unreviewed startup input: " + name)
        inputs[name] = data.decode("utf-8")

    alarms = replace_exact(inputs["libraries/alarms.c"], '#include "inc/alarms.h"',
                           '#include <alarms.h>')
    alarms = replace_exact(alarms, "    SystemAlarmsInitialize();", """    /* Registration normally precedes this call; duplicate initialization
     * returns -2. Preserve the existing object, including critical alarms. */
    if (!SystemAlarmsHandle() && SystemAlarmsInitialize() != 0) {
        return -1;
    }""")
    alarms = replace_exact(alarms, "    lock = xSemaphoreCreateRecursiveMutex();", """    lock = xSemaphoreCreateRecursiveMutex();
    if (!lock) {
        return -1;
    }""")

    events = replace_exact(inputs["uavobjects/eventdispatcher.c"],
        "    mQueue = xQueueCreate(MAX_QUEUE_SIZE, sizeof(EventCallbackInfo));", """    mQueue = xQueueCreate(MAX_QUEUE_SIZE, sizeof(EventCallbackInfo));
    if (!mQueue) {
        vSemaphoreDelete(mMutex);
        mMutex = NULL;
        return -1;
    }""")
    anchor = "    eventSchedulerCallback = PIOS_CALLBACKSCHEDULER_Create(&eventTask, CALLBACK_PRIORITY, TASK_PRIORITY, CALLBACKINFO_RUNNING_EVENTDISPATCHER, STACK_SIZE * 4);"
    events = replace_exact(events, anchor, anchor + """
    if (!eventSchedulerCallback) {
        vQueueDelete(mQueue);
        mQueue = NULL;
        vSemaphoreDelete(mMutex);
        mMutex = NULL;
        return -1;
    }
    /* Dispatch marks this callback pending even when its binary signal was
     * already full. Its zero return is not a lost-registration indication. */""")
    events = replace_exact(events,
        "    if (objEntry == NULL) {\n        return -1;\n    }", """    if (objEntry == NULL) {
        xSemaphoreGiveRecursive(mMutex);
        return -1;
    }""")

    outputs = {"alarms.c": alarms, "eventdispatcher.c": events}
    # Refuse aliases before writing either file, so generated output cannot
    # mutate a source file (or another file) through a symlink/hardlink.
    for name in outputs:
        target = output / name
        if target.is_symlink() or (target.exists() and
                (not target.is_file() or target.stat().st_nlink != 1)):
            raise ValueError("output is not an unaliased regular file: " + name)
    output.mkdir(parents=True, exist_ok=True)
    for name, code in outputs.items():
        target = output / name
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
