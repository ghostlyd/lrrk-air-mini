#!/usr/bin/env python3
"""Generate the pinned LiteWing four-axis outer loop without simulator features.

The external checkout is read-only. This bounds fix preserves the selected
target's direct thrust publication; it does not enable altitude control.
"""
import argparse
import hashlib
from pathlib import Path

from prepare_startup import replace_exact

PIN = "a89228f3c6a3700cccb41b35bcf886672e901c6b18c6c851f11fcbeeaa9bb314"


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("output must be separate from the source subtree and its ancestors")
    path = (source / "Stabilization/outerloop.c").resolve()
    if source not in path.parents:
        raise ValueError("stabilization input escapes source subtree")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != PIN:
        raise ValueError("unreviewed stabilization input: Stabilization/outerloop.c")
    code = data.decode("utf-8")
    code = replace_exact(code, "// Private constants", """/* LiteWing-only adaptation: do not silently select different thrust semantics. */
#if defined(SIMPOSIX) || defined(REVOLUTION)
#error "LiteWing outer loop requires the non-simulator, non-altitude target"
#endif
_Static_assert(AXES == 4, "review outer-loop storage for changed axis count");
_Static_assert(STABILIZATIONSTATUS_OUTERLOOP_THRUST == 3, "review thrust axis mapping");

// Private constants""")
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
    destination = output / "outerloop.c"
    if destination.is_symlink():
        raise ValueError("output file must not be a symlink")
    output.mkdir(parents=True, exist_ok=True)
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
