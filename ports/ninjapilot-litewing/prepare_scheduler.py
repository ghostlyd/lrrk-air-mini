#!/usr/bin/env python3
"""Generate target-only checked scheduler lifecycle/System sources; never flash."""
import argparse
import hashlib
from pathlib import Path
from prepare_startup import replace_exact

ROOT = Path(__file__).resolve().parent
PINS = {
    "pios/common/pios_callbackscheduler.c": "db96ab58cee5988f405980570de631da5626cd8df71654fb4aabc754cb87c01b",
    "modules/System/systemmod.c": "9ec818dcdf55e33d99e005ca618b07abdd365e9e5bcb280cabbeb45f16d2a150",
}


def replace_function(code, signature, replacement):
    if code.count(signature) != 1:
        raise ValueError("scheduler function anchor changed")
    start = code.index(signature)
    end = code.index("\n}\n", start) + 3
    return code[:start] + replacement.rstrip() + "\n" + code[end:]


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("output must be separate from source and ancestors")
    codes = {}
    for name, digest in PINS.items():
        input_path = (source / name).resolve()
        if source not in input_path.parents:
            raise ValueError("input escapes source subtree: " + name)
        data = input_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("unreviewed scheduler input: " + name)
        codes[Path(name).name] = data.decode("utf-8")
    scheduler = codes["pios_callbackscheduler.c"]
    scheduler = replace_exact(scheduler, "    xTaskHandle callbackSchedulerTaskHandle;",
        "    xTaskHandle callbackSchedulerTaskHandle;\n    bool monitorRegistered;")
    scheduler = replace_exact(scheduler, "static bool schedulerStarted;",
        "static bool schedulerStarted;\nstatic bool schedulerStartAttempted;")
    scheduler = replace_exact(scheduler, "    schedulerStarted = false;",
        "    schedulerStarted = false;\n    schedulerStartAttempted = false;")
    for signature, fragment in (("int32_t PIOS_CALLBACKSCHEDULER_Start()", "scheduler_start.inc"),
        ("DelayedCallbackInfo *PIOS_CALLBACKSCHEDULER_Create(", "scheduler_create.inc")):
        scheduler = replace_function(scheduler, signature, (ROOT / "target/startup" / fragment).read_text())
    codes["pios_callbackscheduler.c"] = scheduler
    system = replace_exact(codes["systemmod.c"], "#include <openpilot.h>",
        "#include <openpilot.h>\n#include <pios_litewing_brushed_pwm.h>")
    # The copy lives in the build directory; retain the pinned public header
    # through the existing System/inc include path, not a copied header.
    system = replace_exact(system, '#include "inc/systemmod.h"', '#include <systemmod.h>')
    system = replace_exact(system, "static xTaskHandle systemTaskHandle;", """static bool systemInitAttempted;
static bool systemStartAttempted;
static bool systemResourcesReady;""")
    system = replace_function(system, "int32_t SystemModStart(void)",
        (ROOT / "target/startup/system_start.inc").read_text())
    system = replace_exact(system, "int32_t SystemModInitialize(void)\n{", """int32_t SystemModInitialize(void)
{
    if (systemInitAttempted) return -1;
    systemInitAttempted = true;""")
    for name in ("SystemSettings", "SystemStats", "FlightStatus", "ObjectPersistence",
                 "TaskInfo", "CallbackInfo", "I2CStats", "WatchdogStatus"):
        system = replace_exact(system, "    " + name + "Initialize();",
            "    if (!" + name + "Handle() && (" + name + "Initialize() != 0 || !" + name + "Handle())) {\n"
            "        return -1;\n    }")
    system = replace_exact(system, "    SystemModStart();", """    systemResourcesReady = true;
    if (SystemModStart() != 0) {
        releaseSystemQueue();
        return -1;
    }""")
    system = replace_exact(system, "    /* create all modules thread */", """    /* Register in the task itself, before any dependent startup. There is
     * no creator-side registration to resurrect a deleted task's handle. */
    if (PIOS_TASK_MONITOR_RegisterTask(TASKINFO_RUNNING_SYSTEM, xTaskGetCurrentTaskHandle()) != 0) {
        stopSystemBeforeConnections(false);
        return;
    }
    /* create all modules thread */""")
    codes["systemmod.c"] = replace_exact(system, "    PIOS_CALLBACKSCHEDULER_Start();", """    if (PIOS_CALLBACKSCHEDULER_Start() != 0) {
        stopSystemBeforeConnections(true);
        return;
    }""")
    for name in codes:
        path = output / name
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
            raise ValueError("output must be an unaliased regular file: " + name)
    output.mkdir(parents=True, exist_ok=True)
    for name, code in codes.items():
        path = output / name
        if not path.exists() or path.read_text() != code: path.write_text(code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        prepare(args.source, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
