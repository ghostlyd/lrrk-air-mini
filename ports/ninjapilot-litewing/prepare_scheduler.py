#!/usr/bin/env python3
"""Generate checked scheduler, System and ManualControl startup copies; never flash."""
import argparse
import hashlib
from pathlib import Path
from prepare_startup import replace_exact

ROOT = Path(__file__).resolve().parent
PINS = {
    "pios/common/pios_callbackscheduler.c": "db96ab58cee5988f405980570de631da5626cd8df71654fb4aabc754cb87c01b",
    "modules/System/systemmod.c": "9ec818dcdf55e33d99e005ca618b07abdd365e9e5bcb280cabbeb45f16d2a150",
    "modules/ManualControl/manualcontrol.c": "9526b9c0058b3727b8e268791cb0049dd7b830ec7d967ee6703fab67b80dc31f",
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
        "#include <openpilot.h>\n#include <pios_litewing_brushed_pwm.h>\n#include <pios_litewing_modules.h>\n#include <pios_litewing_readiness.h>\n#include <pios_litewing_wifi_command.h>")
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
    system = replace_exact(system, "    MODULE_TASKCREATE_ALL;", """    if (PIOS_LiteWing_ModulesStart() != 0) {
        stopSystemBeforeConnections(true);
        return;
    }""")
    system = replace_exact(system, "    PIOS_CALLBACKSCHEDULER_Start();", """    if (PIOS_CALLBACKSCHEDULER_Start() != 0) {
        stopSystemBeforeConnections(true);
        return;
    }""")
    system = replace_exact(system, "    ObjectPersistenceConnectQueue(objectPersistenceQueue);",
        "    bool wifi_connections_ready = (ObjectPersistenceConnectQueue(objectPersistenceQueue) == 0);")
    system = replace_exact(system, "    HwSettingsConnectCallback(checkSettingsUpdatedCb);",
        "    wifi_connections_ready &= (HwSettingsConnectCallback(checkSettingsUpdatedCb) == 0);")
    system = replace_exact(system, "    SystemSettingsConnectCallback(checkSettingsUpdatedCb);", """    wifi_connections_ready &= (SystemSettingsConnectCallback(checkSettingsUpdatedCb) == 0);
    /* Optional network task failure must not stop System or USB recovery.
     * Creation is not AP readiness; the task validates credentials first. */
    if (wifi_connections_ready) (void)lw_wifi_command_start();""")
    codes["systemmod.c"] = replace_exact(system, "#if defined(PIOS_INCLUDE_IAP)", """    if (PIOS_LiteWing_ConfirmBootReady() != 0) {
        stopSystemBeforeConnections(true);
        return;
    }
#if defined(PIOS_INCLUDE_IAP)""")
    manual = replace_exact(codes["manualcontrol.c"], '#include "inc/manualcontrol.h"',
        '#include <manualcontrol.h>')
    manual = replace_exact(manual, "static DelayedCallbackInfo *callbackHandle;", """static DelayedCallbackInfo *callbackHandle;
static bool manualControlInitAttempted;
static bool manualControlResourcesReady;
static bool manualControlStartAttempted;""")
    manual = replace_function(manual, "int32_t ManualControlStart()",
        (ROOT / "target/startup/manual_control_start.inc").read_text())
    manual = replace_exact(manual, "int32_t ManualControlInitialize()\n{", """int32_t ManualControlInitialize(void)
{
    if (manualControlInitAttempted) return -1;
    manualControlInitAttempted = true;""")
    for name in ("ManualControlCommand", "FlightStatus", "ManualControlSettings",
                 "FlightModeSettings", "SystemSettings", "StabilizationSettings",
                 "VtolSelfTuningStats", "VtolPathFollowerSettings"):
        manual = replace_exact(manual, "    " + name + "Initialize();",
            "    if (!" + name + "Handle() && (" + name + "Initialize() != 0 || !" + name + "Handle())) {\n"
            "        return -1;\n    }")
    for name in ("VtolPathFollowerSettings", "SystemSettings"):
        manual = replace_exact(manual, "    " + name + "ConnectCallback(&SettingsUpdatedCb);",
            "    if (" + name + "ConnectCallback(&SettingsUpdatedCb) != 0) return -1;")
    anchor = "    callbackHandle = PIOS_CALLBACKSCHEDULER_Create(&manualControlTask, CALLBACK_PRIORITY, CBTASK_PRIORITY, CALLBACKINFO_RUNNING_MANUALCONTROL, STACK_SIZE_BYTES);"
    manual = replace_exact(manual, anchor, anchor + "\n    if (!callbackHandle) return -1;")
    codes["manualcontrol.c"] = replace_exact(manual,
        "    if (!callbackHandle) return -1;\n\n    return 0;\n}",
        "    if (!callbackHandle) return -1;\n    manualControlResourcesReady = true;\n\n    return 0;\n}")
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
