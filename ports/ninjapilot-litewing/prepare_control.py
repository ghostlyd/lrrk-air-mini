#!/usr/bin/env python3
"""Generate hash-checked LiteWing control consumers without editing upstream."""
import argparse
import hashlib
from pathlib import Path

PINS = {
    "Receiver/receiver.c": "0a9395a6335524700ec7ded9993fb256e1058471b62ef71246a50b98dcee82f9",
    "Actuator/actuator.c": "4c5d155937f4f61e482cad7e7121d417574aba8d3f360994d763f061e497b9e7",
}


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
        '#include <systemsettings.h>\n#include "litewing_thrust_control.h"')
    receiver = replace_exact(receiver, "        SystemSettingsThrustControlGet(&thrustType);", """        if (!LiteWingThrustControlRead(&thrustType)) {
            /* Do not retain stale thrust or connection history on bad settings. */
            AlarmsSet(SYSTEMALARMS_ALARM_RECEIVER, SYSTEMALARMS_ALARM_CRITICAL);
            cmd.Connected = MANUALCONTROLCOMMAND_CONNECTED_FALSE;
            cmd.Throttle = cmd.Thrust = -1.0f;
            cmd.Roll = cmd.Pitch = cmd.Yaw = cmd.Collective = 0.0f;
            connected_count = disconnected_count = 0;
            ManualControlCommandSet(&cmd);
            continue;
        }""")
    actuator = replace_exact(inputs["Actuator/actuator.c"], "#include <systemsettings.h>",
        '#include <systemsettings.h>\n#include "litewing_thrust_control.h"')
    actuator = replace_exact(actuator,
        "static SystemSettingsThrustControlOptions thrustType = SYSTEMSETTINGS_THRUSTCONTROL_THROTTLE;\n", "")
    actuator = replace_exact(actuator, "    SystemSettingsThrustControlGet(&thrustType);\n", "")
    actuator = replace_exact(actuator, "        // read in throttle and collective -demultiplex thrust", """        /* Read a local, checked mode each cycle; no asynchronous cached enum. */
        SystemSettingsThrustControlOptions thrustType;
        if (!LiteWingThrustControlRead(&thrustType)) {
            setFailsafe();
            continue;
        }

        // read in throttle and collective -demultiplex thrust""")
    # All inputs/anchors validated before writes. Preserve original GPL notices.
    output.mkdir(parents=True, exist_ok=True)
    for name, code in (("receiver.c", receiver), ("actuator.c", actuator)):
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
