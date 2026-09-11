#include "pios_litewing_modules.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <stdbool.h>
static const char *scenario;
static int inits, starts, battery_inits, battery_starts;
static bool health_registered;
int32_t LiteWingImuHealthInitialize(void) { assert(inits==5); health_registered=true; return 0; }
int32_t LiteWingImuHealthStart(void) { assert(starts==7); return 0; }
#define MODULE(Name, Index) \
int32_t Name##Initialize(void) { assert(inits++==Index); if(Index==5) assert(health_registered); return 0; } \
int32_t Name##Start(void) { assert(inits==7 && starts++==Index); return 0; }
MODULE(Attitude,0) MODULE(Stabilization,1) MODULE(Actuator,2)
MODULE(Receiver,3) MODULE(ManualControl,4) MODULE(Telemetry,5)
int32_t LiteWingBatteryInitialize(void) {
    assert(inits++==6); battery_inits++; return !strcmp(scenario,"init-fail")?-9:0;
}
int32_t LiteWingBatteryStart(void) {
    assert(inits==7 && starts++==6); battery_starts++; return !strcmp(scenario,"start-fail")?-9:0;
}
int main(int argc,char **argv) {
    assert(argc==2); scenario=argv[1];
    assert(PIOS_LiteWing_ModulesStart()!=0 && inits==0 && starts==0);
    int rc=PIOS_LiteWing_ModulesInitialize();
    assert(battery_inits==1 && inits==7);
    assert(PIOS_LiteWing_ModulesInitialize()!=0 && inits==7);
    if(!strcmp(scenario,"init-fail")) {
        assert(rc==-9 && PIOS_LiteWing_ModulesStart()!=0 && starts==0);
    } else {
        assert(rc==0);
        rc=PIOS_LiteWing_ModulesStart();
        assert(battery_starts==1 && starts==7);
        assert(rc==(!strcmp(scenario,"start-fail")?-9:0));
        assert(PIOS_LiteWing_ModulesStart()!=0 && starts==7);
    }
    puts("PASS"); return 0;
}
