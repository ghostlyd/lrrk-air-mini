#!/usr/bin/env python3
"""Generate hash-checked LiteWing control consumers without editing upstream."""
import argparse
import hashlib
from pathlib import Path
from prepare_input_startup import prepare_input

PINS = {
    "Attitude/attitude.c": "73386b3c3e73e1f3296937fd1bed6dbf0e91bf778dc86b67e0455ac0e166bd1f",
    "Receiver/receiver.c": "0a9395a6335524700ec7ded9993fb256e1058471b62ef71246a50b98dcee82f9",
    "Actuator/actuator.c": "4c5d155937f4f61e482cad7e7121d417574aba8d3f360994d763f061e497b9e7",
}
ROOT = Path(__file__).resolve().parent


def replace_exact(text, old, new):
    if text.count(old) != 1:
        raise ValueError("pinned control adaptation anchor changed")
    return text.replace(old, new)


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents:
        raise ValueError("output must be outside the source checkout subtree")
    inputs = {}
    for name, digest in PINS.items():
        data = (source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("unreviewed control input: " + name)
        inputs[name] = data.decode("utf-8")
    receiver = replace_exact(inputs["Receiver/receiver.c"], "#include <systemsettings.h>",
        '#include <systemsettings.h>\n#include "litewing_thrust_control.h"\n#include "pios_litewing_brushed_pwm.h"')
    receiver = replace_exact(receiver, "        SystemSettingsThrustControlGet(&thrustType);", """        if (!LiteWingThrustControlRead(&thrustType)) {
            /* Do not retain stale thrust or connection history on bad settings. */
            AlarmsSet(SYSTEMALARMS_ALARM_RECEIVER, SYSTEMALARMS_ALARM_CRITICAL);
            cmd.Connected = MANUALCONTROLCOMMAND_CONNECTED_FALSE;
            cmd.Throttle = cmd.Thrust = -1.0f;
            cmd.Roll = cmd.Pitch = cmd.Yaw = cmd.Collective = 0.0f;
            connected_count = disconnected_count = 0;
            if (ManualControlCommandSet(&cmd) != 0) {
                /* Do not bypass read-only metadata to overwrite a stale command.
                 * Failed fault publication requires output shutdown until reboot. */
                PIOS_LiteWing_BrushedPWM_Shutdown();
            }
            continue;
        }""")
    actuator = replace_exact(inputs["Actuator/actuator.c"], "#include <systemsettings.h>",
        '#include <systemsettings.h>\n#include "litewing_thrust_control.h"\n#include "pios_litewing_brushed_pwm.h"\n#include "litewing_contract.h"')
    actuator = replace_exact(actuator,
        """            if (mixer_type == MIXERSETTINGS_MIXER1TYPE_DISABLED) {
                // Set to minimum if disabled.""",
        """            if (mixer_type == MIXERSETTINGS_MIXER1TYPE_DISABLED) {
                /* Only ordinary PWM slots with no LiteWing output are inactive.
                 * Preserve physical remaps and other channel-type semantics. */
                if ((unsigned)ct >= LITEWING_OUTPUT_CHANNELS &&
                    actuatorSettings.ChannelType[ct] == ACTUATORSETTINGS_CHANNELTYPE_PWM &&
                    actuatorSettings.ChannelAddr[ct] >= LITEWING_OUTPUT_CHANNELS) {
                    command.Channel[ct] = 0;
                }
                // Set to minimum if disabled.""")
    actuator = replace_exact(actuator, "static xTaskHandle taskHandle;", """static bool actuatorInitAttempted;
static bool actuatorResourcesReady;
static bool actuatorStartAttempted;""")
    start = actuator.index("int32_t ActuatorStart()")
    end = actuator.index("MODULE_INITCALL(ActuatorInitialize, ActuatorStart);")
    actuator = replace_exact(actuator, actuator[start:end],
        (ROOT / "target/startup/actuator_start.inc").read_text().rstrip() + "\n")
    actuator = replace_exact(actuator,
        "static void actuatorTask(__attribute__((unused)) void *parameters)\n{",
        """static void actuatorTask(__attribute__((unused)) void *parameters)
{
    /* The task owns its monitor handle. It may execute and retire before
     * xTaskCreate returns; the creator must never republish its handle. */
    if (PIOS_TASK_MONITOR_RegisterTask(TASKINFO_RUNNING_ACTUATOR, xTaskGetCurrentTaskHandle()) != 0) {
        PIOS_LiteWing_BrushedPWM_Shutdown();
        AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_CRITICAL);
        /* Failed monitor registration publishes no handle. The connected
         * object queue stays allocated; callbacks may still refer to it. */
        vTaskDelete(NULL);
        return;
    }
    SettingsUpdatedCb(NULL);
    MixerSettingsUpdatedCb(NULL);
    ActuatorSettingsUpdatedCb(NULL);""")
    actuator = replace_exact(actuator,
        "static SystemSettingsThrustControlOptions thrustType = SYSTEMSETTINGS_THRUSTCONTROL_THROTTLE;\n", "")
    actuator = replace_exact(actuator, "    SystemSettingsThrustControlGet(&thrustType);\n", "")
    actuator = replace_exact(actuator,
        "static float lastResult[MAX_MIX_ACTUATORS] = { 0 };",
        """static float lastResult[MAX_MIX_ACTUATORS] = { 0 };
static float lastFilteredResult[MAX_MIX_ACTUATORS];
static float lastThrottleDesired;""")
    actuator = replace_exact(actuator, "            static float lastThrottleDesired = 0.0f;\n", "")
    actuator = replace_exact(actuator, "    static float lastFilteredResult[MAX_MIX_ACTUATORS];\n", "")
    actuator = replace_exact(actuator, "static void setFailsafe()\n{", """static void setFailsafe()
{
    /* Fault recovery must start from zero, never a pre-fault powered history. */
    lastThrottleDesired = 0.0f;
    memset(lastResult, 0, sizeof(lastResult));
    memset(filterAccumulator, 0, sizeof(filterAccumulator));
    memset(lastFilteredResult, 0, sizeof(lastFilteredResult));""")
    actuator = replace_exact(actuator, "        // read in throttle and collective -demultiplex thrust", """        /* Read a local, checked mode each cycle; no asynchronous cached enum. */
        SystemSettingsThrustControlOptions thrustType;
        if (!LiteWingThrustControlRead(&thrustType)) {
            setFailsafe();
            continue;
        }

        // read in throttle and collective -demultiplex thrust""")
    receiver = prepare_input(receiver, "Receiver")
    attitude = prepare_input(inputs["Attitude/attitude.c"], "Attitude")
    attitude = replace_exact(attitude, '#include <openpilot.h>',
        '#include <openpilot.h>\n#include "litewing_attitude_trace_module.h"')
    attitude = replace_exact(attitude, '    AttitudeStateSet(&attitudeState);',
        '''    AttitudeStateSet(&attitudeState);
#if CONFIG_LRRK_ATTITUDE_TRACE
    /* Same estimator update; PWM in the callee is a separate qualified snapshot. */
    const float trace_gyro[3] = {gyrosData->x, gyrosData->y, gyrosData->z};
    LiteWingAttitudeTraceRecord(dT, accels, trace_gyro, gyros, rpy_temp);
#endif''')
    # All inputs/anchors validated before writes. Preserve original GPL notices.
    output.mkdir(parents=True, exist_ok=True)
    for name, code in (("receiver.c", receiver), ("actuator.c", actuator), ("attitude.c", attitude)):
        destination = output / name
        if not destination.exists() or destination.read_text() != code:
            destination.write_text(code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        prepare(args.source, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
