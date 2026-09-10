#include "pios.h"
#include "uavobjectmanager.h"
#include "manualcontrolsettings.h"
#include "flightstatus.h"
#include "pios_litewing_pilot_mapping.h"
#include <string.h>
static ManualControlSettingsData settings;
static FlightStatusData flight;
static int failure;
static unsigned reads;
static int late_arm;
UAVObjHandle ManualControlSettingsHandle(void) { return &settings; }
UAVObjHandle FlightStatusHandle(void) { return &flight; }
int32_t UAVObjGetData(UAVObjHandle handle, void *out)
{
    ++reads;
    if ((unsigned)failure==reads) return -1;
    if (late_arm && reads==3) flight.Armed=FLIGHTSTATUS_ARMED_ARMED;
    if (handle==&settings) memcpy(out,&settings,sizeof(settings));
    else { assert(handle==&flight); memcpy(out,&flight,sizeof(flight)); }
    return 0;
}
int main(int argc, char **argv)
{
    assert(argc==2);
    memset(&settings.ChannelGroups,MANUALCONTROLSETTINGS_CHANNELGROUPS_NONE,
           sizeof(settings.ChannelGroups));
#define SET(name,number) do { settings.ChannelGroups.name=MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS; \
    settings.ChannelNumber.name=number; settings.ChannelMin.name=1000; \
    settings.ChannelNeutral.name=1500; settings.ChannelMax.name=2000; } while(0)
    SET(Throttle,4); SET(Roll,2); SET(Pitch,3); SET(Yaw,1); SET(FlightMode,5);
    flight.Armed=FLIGHTSTATUS_ARMED_DISARMED;
    if (!strcmp(argv[1],"armed")) flight.Armed=FLIGHTSTATUS_ARMED_ARMED;
    if (!strcmp(argv[1],"arming")) flight.Armed=FLIGHTSTATUS_ARMED_ARMING;
    if (!strcmp(argv[1],"read-error")) failure=1;
    if (!strcmp(argv[1],"settings-read-error")) failure=2;
    if (!strcmp(argv[1],"recheck-error")) failure=3;
    if (!strcmp(argv[1],"late-arm")) late_arm=1;
    if (!strcmp(argv[1],"wrong-group")) settings.ChannelGroups.Yaw=MANUALCONTROLSETTINGS_CHANNELGROUPS_PWM;
    if (!strcmp(argv[1],"accessory")) settings.ChannelGroups.Accessory0=MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS;
    if (!strcmp(argv[1],"duplicate")) settings.ChannelNumber.Yaw=4;
    if (!strcmp(argv[1],"bad-calibration")) settings.ChannelMin.Roll=2001;
    struct lw_pilot_channel mapping[5];
    memset(mapping,0xa5,sizeof(mapping));
    int result=PIOS_LiteWing_PilotReadAdmissionMapping(mapping);
    if (!strcmp(argv[1],"valid")) {
        assert(result==0);
        assert(mapping[0].channel==4 && mapping[3].channel==1);
        assert(mapping[0].minimum==1000 && mapping[1].neutral==1500);
    } else {
        assert(result==-1);
        const unsigned char *bytes=(const unsigned char *)mapping;
        for (unsigned i=0;i<sizeof(mapping);++i) assert(bytes[i]==0);
    }
    return 0;
}
