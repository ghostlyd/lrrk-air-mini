/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "pios.h"
#include "uavobjectmanager.h"
#include "manualcontrolsettings.h"
#include "flightstatus.h"
#include "pios_litewing_pilot_mapping.h"
#include <string.h>

int PIOS_LiteWing_PilotReadAdmissionMapping(struct lw_pilot_channel out[5])
{
    if (!out) return -1;
    memset(out,0,5*sizeof(*out));
    ManualControlSettingsData settings;
    FlightStatusData flight;
    struct lw_pilot_channel mapping[5] = {0};
    uint16_t neutral[8] = {1500,1500,1500,1500,1500,1500,1500,1500};
    if (FlightStatusGet(&flight)!=0 || flight.Armed!=FLIGHTSTATUS_ARMED_DISARMED ||
        ManualControlSettingsGet(&settings)!=0) return -1;
    if (settings.ChannelGroups.Collective!=MANUALCONTROLSETTINGS_CHANNELGROUPS_NONE ||
        settings.ChannelGroups.Accessory0!=MANUALCONTROLSETTINGS_CHANNELGROUPS_NONE ||
        settings.ChannelGroups.Accessory1!=MANUALCONTROLSETTINGS_CHANNELGROUPS_NONE ||
        settings.ChannelGroups.Accessory2!=MANUALCONTROLSETTINGS_CHANNELGROUPS_NONE)
        return -1;
#define LOAD(name,index) do { \
    if (settings.ChannelGroups.name!=MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS || \
        settings.ChannelNumber.name<1 || settings.ChannelNumber.name>8) return -1; \
    mapping[index].channel=settings.ChannelNumber.name; \
    mapping[index].minimum=settings.ChannelMin.name; \
    mapping[index].neutral=settings.ChannelNeutral.name; \
    mapping[index].maximum=settings.ChannelMax.name; \
    neutral[mapping[index].channel-1]=(uint16_t)((index)==0 ? \
        mapping[index].minimum : mapping[index].neutral); \
} while (0)
    LOAD(Throttle,0);
    LOAD(Roll,1);
    LOAD(Pitch,2);
    LOAD(Yaw,3);
    LOAD(FlightMode,4);
#undef LOAD
    if (!lw_pilot_neutral(mapping,neutral)) return -1;
    if (FlightStatusGet(&flight)!=0 || flight.Armed!=FLIGHTSTATUS_ARMED_DISARMED)
        return -1;
    memcpy(out,mapping,sizeof(mapping));
    return 0;
}
