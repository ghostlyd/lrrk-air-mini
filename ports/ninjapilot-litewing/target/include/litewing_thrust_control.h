/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LITEWING_THRUST_CONTROL_H
#define LITEWING_THRUST_CONTROL_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <systemsettings.h>

/* The generated void field getter discards the manager's return code and
 * writes ONE BYTE, not an enum. Use its exact field layout with a checked read.
 * NONE is a schema value, but cannot select a thrust source on this target.
 * Publish a fully initialized enum only after successful validation. */
static inline bool LiteWingThrustControlRead(SystemSettingsThrustControlOptions *out)
{
    uint8_t value = UINT8_MAX;
    if (!out || UAVObjGetDataField(SystemSettingsHandle(), &value,
            offsetof(SystemSettingsData, ThrustControl), sizeof(value)) != 0) {
        return false;
    }
    switch (value) {
    case SYSTEMSETTINGS_THRUSTCONTROL_THROTTLE:
    case SYSTEMSETTINGS_THRUSTCONTROL_COLLECTIVE:
        *out = (SystemSettingsThrustControlOptions)value;
        return true;
    default:
        return false;
    }
}
#endif
