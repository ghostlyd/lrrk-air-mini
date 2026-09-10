#!/usr/bin/env python3
"""Generate pinned LiteWing Stabilization copies without simulator features.

The external checkout is read-only. The outer-loop bounds fix preserves the
selected target's direct thrust publication; it does not enable altitude control.
"""
import argparse
import hashlib
from pathlib import Path

from prepare_startup import replace_exact

PINS = {
    "stabilization.c": "0bf808ebe597aa76abefbe026e1d40ade38ec2fe5645400aac7ea6cd2b347918",
    "outerloop.c": "a89228f3c6a3700cccb41b35bcf886672e901c6b18c6c851f11fcbeeaa9bb314",
    "innerloop.c": "9de7fe11cba25a25e226414471d10001824c07e5345cfcfe763960a2eae0d1b9",
}


def replace_function(code, signature, replacement):
    if code.count(signature) != 1:
        raise ValueError("stabilization function anchor changed")
    start = code.index(signature)
    end = code.index("\n}\n", start) + 3
    return code[:start] + replacement.rstrip() + "\n" + code[end:]


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("output must be separate from the source subtree and its ancestors")
    inputs = {}
    for name, digest in PINS.items():
        path = (source / "Stabilization" / name).resolve()
        if source not in path.parents:
            raise ValueError("stabilization input escapes source subtree: " + name)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("unreviewed stabilization input: Stabilization/" + name)
        inputs[name] = data.decode("utf-8")
    code = inputs["outerloop.c"]
    code = replace_exact(code, "// Private constants", """/* LiteWing-only adaptation: do not silently select different thrust semantics. */
#if defined(SIMPOSIX) || defined(REVOLUTION)
#error "LiteWing outer loop requires the non-simulator, non-altitude target"
#endif
_Static_assert(AXES == 4, "review outer-loop storage for changed axis count");
_Static_assert(STABILIZATIONSTATUS_OUTERLOOP_THRUST == 3, "review thrust axis mapping");

// Private constants""")
    code = replace_exact(code, "static DelayedCallbackInfo *callbackHandle;", """static DelayedCallbackInfo *callbackHandle;
static bool outerloopInitAttempted;""")
    code = replace_exact(code, "void stabilizationOuterloopInit()\n{", """int32_t PIOS_LiteWing_StabilizationOuterloopInitialize(void)
{
    if (outerloopInitAttempted) return -1;
    outerloopInitAttempted = true;""")
    for name in ("RateDesired", "StabilizationDesired", "AttitudeState",
                 "StabilizationStatus", "FlightStatus", "ManualControlCommand"):
        code = replace_exact(code, "    " + name + "Initialize();",
            "    if (!" + name + "Handle() && (" + name + "Initialize() != 0 || !" +
            name + "Handle())) return -1;")
    create = "    callbackHandle = PIOS_CALLBACKSCHEDULER_Create(&stabilizationOuterloopTask, CALLBACK_PRIORITY, CALLBACK_TASK_STABILIZATIONOUTERLOOP, CALLBACKINFO_RUNNING_STABILIZATION0, STACK_SIZE_BYTES);"
    code = replace_exact(code, create, create + "\n    if (!callbackHandle) return -1;")
    code = replace_exact(code, "    AttitudeStateConnectCallback(AttitudeStateUpdatedCb);\n}", """    if (AttitudeStateConnectCallback(AttitudeStateUpdatedCb) != 0) return -1;
    return 0;
}

void stabilizationOuterloopInit(void)
{
    (void)PIOS_LiteWing_StabilizationOuterloopInitialize();
}""")
    start = code.index("#ifdef SIMPOSIX\n    // AXES is 4")
    end = code.index("    int t;", start)
    code = replace_exact(code, code[start:end], """    /* The per-axis loop includes Thrust at index 3. Both buffers must
     * cover all four axes even though this target publishes direct thrust. */
    float stabilizationDesiredAxis[AXES] = {stabilizationDesired.Roll, stabilizationDesired.Pitch, stabilizationDesired.Yaw, stabilizationDesired.Thrust};
    float rateDesiredAxis[AXES] = {rateDesired.Roll, rateDesired.Pitch, rateDesired.Yaw, rateDesired.Thrust};
""")
    start = code.index("    // Thrust has no outer-loop PID of its own")
    end = code.index("    rateDesired.Thrust = stabilizationDesired.Thrust;", start)
    code = replace_exact(code, code[start:end], """    /* Preserve LiteWing's existing direct-thrust publication. The loop
     * does visit axis 3; no REVOLUTION altitude controller is selected. */
""")
    code = replace_exact(code, "        float rpy_desired[3];", """        /* UAVObject fields are packed scalars, not float arrays. Copy them
         * into aligned, bounded storage before indexed quaternion math. */
        const float rpy_current[3] = {attitudeState.Roll, attitudeState.Pitch, attitudeState.Yaw};
        const float q_current[4] = {attitudeState.q1, attitudeState.q2, attitudeState.q3, attitudeState.q4};
        float rpy_desired[3];""")
    code = replace_exact(code, "((float *)&attitudeState.Roll)[t]", "rpy_current[t]")
    code = replace_exact(code, "quat_mult(q_desired, &attitudeState.q1, q_error);",
                         "quat_mult(q_desired, q_current, q_error);")
    inner = inputs["innerloop.c"]
    inner = replace_exact(inner, "static DelayedCallbackInfo *callbackHandle;", """static DelayedCallbackInfo *callbackHandle;
static bool innerloopInitAttempted;""")
    inner = replace_exact(inner, "void stabilizationInnerloopInit()\n{", """int32_t PIOS_LiteWing_StabilizationInnerloopInitialize(void)
{
    if (innerloopInitAttempted) return -1;
    innerloopInitAttempted = true;""")
    inner = replace_exact(inner,
        "    StabilizationDesiredInitialize();\n    ActuatorDesiredInitialize();",
        "    StabilizationDesiredInitialize();")
    for name in ("RateDesired", "ActuatorDesired", "GyroState", "StabilizationStatus",
                 "FlightStatus", "ManualControlCommand", "StabilizationDesired"):
        inner = replace_exact(inner, "    " + name + "Initialize();",
            "    if (!" + name + "Handle() && (" + name + "Initialize() != 0 || !" +
            name + "Handle())) return -1;")
    create = "    callbackHandle = PIOS_CALLBACKSCHEDULER_Create(&stabilizationInnerloopTask, CALLBACK_PRIORITY, CBTASK_PRIORITY, CALLBACKINFO_RUNNING_STABILIZATION1, STACK_SIZE_BYTES);"
    inner = replace_exact(inner, create, create + "\n    if (!callbackHandle) return -1;")
    inner = replace_exact(inner, "    GyroStateConnectCallback(GyroStateUpdatedCb);",
                          "    if (GyroStateConnectCallback(GyroStateUpdatedCb) != 0) return -1;")
    inner = replace_exact(inner, """    // schedule dead calls every FAILSAFE_TIMEOUT_MS to have the watchdog cleared
    PIOS_CALLBACKSCHEDULER_Schedule(callbackHandle, FAILSAFE_TIMEOUT_MS, CALLBACK_UPDATEMODE_LATER);
}""", """    // A fresh callback must acquire its first failsafe schedule.
    if (PIOS_CALLBACKSCHEDULER_Schedule(callbackHandle, FAILSAFE_TIMEOUT_MS,
                                        CALLBACK_UPDATEMODE_LATER) != 1) return -1;
    return 0;
}

void stabilizationInnerloopInit(void)
{
    (void)PIOS_LiteWing_StabilizationInnerloopInitialize();
}""")
    stabilization = inputs["stabilization.c"]
    stabilization = replace_exact(stabilization,
        "static uint8_t previousArmedStatus = FLIGHTSTATUS_ARMED_DISARMED;", """static uint8_t previousArmedStatus = FLIGHTSTATUS_ARMED_DISARMED;
static bool stabilizationInitAttempted;
static bool stabilizationResourcesReady;
static bool stabilizationStartAttempted;
static bool startupApplying;
static bool startupApplyFailed;""")
    declaration = "static void ArmedStatusUpdatedCb(UAVObjEvent *ev);"
    stabilization = replace_exact(stabilization, declaration, declaration + """
int32_t PIOS_LiteWing_StabilizationOuterloopInitialize(void);
int32_t PIOS_LiteWing_StabilizationInnerloopInitialize(void);

static void noteStartupApplyFailure(void)
{
    if (startupApplying) startupApplyFailed = true;
}""")
    stabilization = replace_function(stabilization, "int32_t StabilizationStart()", """
int32_t StabilizationStart(void)
{
    if (!stabilizationResourcesReady || stabilizationStartAttempted) return -1;
    stabilizationStartAttempted = true;
#ifdef PIOS_INCLUDE_WDG
    if (!PIOS_WDG_RegisterFlag(PIOS_WDG_STABILIZATION)) return -1;
#endif
    if (StabilizationSettingsConnectCallback(SettingsUpdatedCb) != 0) return -1;
    if (ManualControlCommandConnectCallback(FlightModeSwitchUpdatedCb) != 0) return -1;
    if (StabilizationBankConnectCallback(BankUpdatedCb) != 0) return -1;
    if (StabilizationSettingsBank1ConnectCallback(SettingsBankUpdatedCb) != 0) return -1;
    if (StabilizationSettingsBank2ConnectCallback(SettingsBankUpdatedCb) != 0) return -1;
    if (StabilizationSettingsBank3ConnectCallback(SettingsBankUpdatedCb) != 0) return -1;
    if (StabilizationDesiredConnectCallback(StabilizationDesiredUpdatedCb) != 0) return -1;
    if (FlightStatusConnectCallback(ArmedStatusUpdatedCb) != 0) return -1;

    startupApplyFailed = false;
    startupApplying = true;
    SettingsUpdatedCb(NULL);
    if (!startupApplyFailed) StabilizationDesiredUpdatedCb(NULL);
    if (!startupApplyFailed) FlightModeSwitchUpdatedCb(NULL);
    if (!startupApplyFailed) BankUpdatedCb(NULL);
    startupApplying = false;
    if (startupApplyFailed) return -1;
    return 0;
}
""")
    stabilization = replace_exact(stabilization, "int32_t StabilizationInitialize()\n{", """int32_t StabilizationInitialize(void)
{
    if (stabilizationInitAttempted) return -1;
    stabilizationInitAttempted = true;""")
    for name in ("StabilizationDesired", "StabilizationSettings", "StabilizationStatus",
                 "StabilizationBank", "StabilizationSettingsBank1", "StabilizationSettingsBank2",
                 "StabilizationSettingsBank3", "RateDesired", "ManualControlCommand",
                 "RelayTuningSettings", "RelayTuning"):
        stabilization = replace_exact(stabilization, "    " + name + "Initialize();",
            "    if (!" + name + "Handle() && (" + name + "Initialize() != 0 || !" +
            name + "Handle())) return -1;")
    stabilization = replace_exact(stabilization, "    sin_lookup_initalize();",
                                  "    if (sin_lookup_initalize() != 0) return -1;")
    stabilization = replace_exact(stabilization,
        "    stabilizationOuterloopInit();\n    stabilizationInnerloopInit();", """    if (PIOS_LiteWing_StabilizationOuterloopInitialize() != 0) return -1;
    if (PIOS_LiteWing_StabilizationInnerloopInitialize() != 0) return -1;""")
    stabilization = replace_exact(stabilization,
        "    pid_zero(&stabSettings.innerPids[2]);\n    return 0;", """    pid_zero(&stabSettings.innerPids[2]);
    stabilizationResourcesReady = true;
    return 0;""")
    stabilization = replace_exact(stabilization,
        "    StabilizationDesiredStabilizationModeGet(&mode);", """    StabilizationDesiredData desired;
    if (StabilizationDesiredGet(&desired) != 0) {
        noteStartupApplyFailure();
        return;
    }""")
    stabilization = replace_exact(stabilization,
        "    for (t = 0; t < AXES; t++) {", """    mode = desired.StabilizationMode;
    for (t = 0; t < AXES; t++) {""")
    stabilization = replace_exact(stabilization, "    StabilizationStatusSet(&status);", """    if (StabilizationStatusSet(&status) != 0) {
        noteStartupApplyFailure();
    }""")
    stabilization = replace_exact(stabilization,
        "    FlightStatusArmedGet(&armedStatus);", """    FlightStatusData flightStatus;
    if (FlightStatusGet(&flightStatus) != 0) {
        noteStartupApplyFailure();
        return;
    }
    armedStatus = flightStatus.Armed;""")
    stabilization = replace_exact(stabilization,
        "    ManualControlCommandFlightModeSwitchPositionGet(&fm);", """    ManualControlCommandData command;
    if (ManualControlCommandGet(&command) != 0) {
        noteStartupApplyFailure();
        return;
    }
    fm = command.FlightModeSwitchPosition;""")
    stabilization = replace_exact(stabilization,
        "    if (cur_flight_mode < 0 || cur_flight_mode >= FLIGHTMODESETTINGS_FLIGHTMODEPOSITION_NUMELEM) {\n        return;\n    }", """    if (cur_flight_mode < 0 || cur_flight_mode >= FLIGHTMODESETTINGS_FLIGHTMODEPOSITION_NUMELEM) {
        noteStartupApplyFailure();
        return;
    }""")
    for name in ("StabilizationSettingsBank1", "StabilizationSettingsBank2",
                 "StabilizationSettingsBank3"):
        stabilization = replace_exact(stabilization,
            "        " + name + "Get((" + name + "Data *)&stabSettings.stabBank);",
            "        if (" + name + "Get((" + name + "Data *)&stabSettings.stabBank) != 0) {\n"
            "            noteStartupApplyFailure();\n            return;\n        }")
    stabilization = replace_exact(stabilization, "    StabilizationBankSet(&stabSettings.stabBank);", """    if (StabilizationBankSet(&stabSettings.stabBank) != 0) {
        noteStartupApplyFailure();
    }""")
    stabilization = replace_exact(stabilization,
        "    StabilizationBankGet(&stabSettings.stabBank);", """    if (StabilizationBankGet(&stabSettings.stabBank) != 0) {
        noteStartupApplyFailure();
        return;
    }""")
    stabilization = replace_exact(stabilization,
        "    StabilizationSettingsGet(&stabSettings.settings);", """    if (StabilizationSettingsGet(&stabSettings.settings) != 0) {
        noteStartupApplyFailure();
        return;
    }""")
    outputs = {
        "stabilization.c": stabilization,
        "outerloop.c": code,
        "innerloop.c": inner,
    }
    for name in outputs:
        destination = output / name
        if destination.is_symlink():
            raise ValueError("output file must not be a symlink: " + name)
        if destination.exists() and not destination.is_file():
            raise ValueError("output file must be a regular file: " + name)
        if destination.exists() and destination.stat().st_nlink != 1:
            raise ValueError("output file must not be a hardlink: " + name)
    output.mkdir(parents=True, exist_ok=True)
    for name, generated in outputs.items():
        destination = output / name
        if not destination.exists() or destination.read_text() != generated:
            destination.write_text(generated)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        prepare(args.source, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
