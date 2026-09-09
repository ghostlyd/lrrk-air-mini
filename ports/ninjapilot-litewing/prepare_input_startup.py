"""Target-only input lifecycle adapters; caller validates complete upstream hashes."""
from pathlib import Path
from prepare_startup import replace_exact

ROOT = Path(__file__).resolve().parent


def replace_entry(code, signature, replacement):
    if code.count(signature) != 1:
        raise ValueError("input lifecycle function anchor changed")
    start = code.index(signature)
    end = code.index("\n}\n", start) + 3
    return code[:start] + replacement.rstrip() + "\n" + code[end:]


def prepare_input(code, module):
    task, monitor, watchdog, suffix = {
        "Attitude": ("AttitudeTask", "ATTITUDE", "ATTITUDE", "void"),
        "Receiver": ("receiverTask", "RECEIVER", "MANUAL", ""),
    }[module]
    code = replace_exact(code, "#include <openpilot.h>",
        '#include <openpilot.h>\n#include "pios_litewing_brushed_pwm.h"')
    code = replace_exact(code, "static xTaskHandle taskHandle;", """static bool inputInitAttempted;
static bool inputResourcesReady;
static bool inputStartAttempted;""")
    start_code = (ROOT / "target/startup/input_start.inc").read_text()
    for old, new in (("INPUT_MODULE_START", module + "Start"), ("INPUT_TASK_FUNCTION", task),
                     ("INPUT_MONITOR_SLOT", "TASKINFO_RUNNING_" + monitor),
                     ("INPUT_WATCHDOG_FLAG", "PIOS_WDG_" + watchdog),
                     ("INPUT_TASK_NAME", '"' + module + '"')):
        start_code = replace_exact(start_code, old, new)
    code = replace_entry(code, f"int32_t {module}Start({suffix})", start_code)
    code = replace_exact(code, f"int32_t {module}Initialize({suffix})\n{{", f"""int32_t {module}Initialize({suffix})
{{
    if (inputInitAttempted) return -1;
    inputInitAttempted = true;""")
    objects = {
        "Attitude": ("AttitudeState", "AttitudeSettings", "AccelGyroSettings", "AccelState", "GyroState", "AccelSensor", "GyroSensor"),
        "Receiver": ("AccessoryDesired", "ManualControlCommand", "ReceiverActivity", "ManualControlSettings", "StabilizationSettings", "VtolPathFollowerSettings", "SystemSettings"),
    }[module]
    for name in objects:
        code = replace_exact(code, f"    {name}Initialize();",
            f"    if (!{name}Handle() && ({name}Initialize() != 0 || !{name}Handle())) return -1;")
    callbacks = {"Attitude": ("AttitudeSettings", "AccelGyroSettings"),
                 "Receiver": ("VtolPathFollowerSettings", "SystemSettings")}[module]
    callback = "settingsUpdatedCb" if module == "Attitude" else "SettingsUpdatedCb"
    for name in callbacks:
        code = replace_exact(code, f"    {name}ConnectCallback(&{callback});",
            f"    if ({name}ConnectCallback(&{callback}) != 0) return -1;")
    # The worker owns its monitor handle and can retire before create returns.
    anchor = f"static void {task}(__attribute__((unused)) void *parameters)\n{{"
    code = replace_exact(code, anchor, anchor + f"""
    if (PIOS_TASK_MONITOR_RegisterTask(TASKINFO_RUNNING_{monitor}, xTaskGetCurrentTaskHandle()) != 0) {{
        stopInputTask(false);
        return;
    }}""")
    if module == "Receiver":
        code = replace_exact(code, "    AccessoryDesiredCreateInstance();\n    AccessoryDesiredCreateInstance();\n", "")
        code = replace_exact(code, "    ManualControlCommandGet(&cmd);\n    FlightStatusGet(&flightStatus);", """    SettingsUpdatedCb(NULL);
    if (ManualControlCommandGet(&cmd) != 0 || FlightStatusGet(&flightStatus) != 0) {
        stopInputTask(true);
        return;
    }""")
        last = "    if (SystemSettingsConnectCallback(&SettingsUpdatedCb) != 0) return -1;"
        code = replace_exact(code, last, last + """
    /* The pinned create API can return a nonzero intended ID on allocation
     * failure. Verify growth, not just its return value. Preserve existing
     * globally-owned instances and stop after any partial allocation error. */
    uint16_t count = UAVObjGetNumInstances(AccessoryDesiredHandle());
    if (count < 1) return -1;
    while (count < 3) {
        uint16_t next = AccessoryDesiredCreateInstance();
        uint16_t actual = UAVObjGetNumInstances(AccessoryDesiredHandle());
        if (next != count || actual != count + 1) return -1;
        count = actual;
    }
    inputResourcesReady = true;""")
    else:
        code = replace_exact(code, "    AttitudeStateGet(&attitude);", "    if (AttitudeStateGet(&attitude) != 0) return -1;")
        code = replace_exact(code, "    AttitudeStateSet(&attitude);", "    if (AttitudeStateSet(&attitude) != 0) return -1;")
        allocation = "        mpu6000_data = pios_malloc(sizeof(PIOS_SENSORS_3Axis_SensorsWithTemp) + sizeof(Vector3i16) * 2);"
        code = replace_exact(code, allocation, "")
        last = "    if (AccelGyroSettingsConnectCallback(&settingsUpdatedCb) != 0) return -1;"
        code = replace_exact(code, last, last + """
#if defined(PIOS_INCLUDE_ICM20602) || defined(PIOS_INCLUDE_MPU6000)
    /* Allocate before task creation. The static module owns this buffer
     * until reboot, including after a later failed startup. */
    if (BOARDISCC3D) {
        mpu6000_data = pios_malloc(sizeof(PIOS_SENSORS_3Axis_SensorsWithTemp) + sizeof(Vector3i16) * 2);
        if (!mpu6000_data) return -1;
    }
#endif
    inputResourcesReady = true;""")
        code = replace_exact(code, "        gyro_test    = ATTITUDE_IMU_DRIVER.test(0);", """        gyro_test    = ATTITUDE_IMU_DRIVER.test(0);
        if (!gyro_test || !ATTITUDE_IMU_DRIVER.get_queue(0)) {
            stopInputTask(true);
            return;
        }""")
    return code
