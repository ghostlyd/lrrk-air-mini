#include "battery_worker_sdk.h"
#include "pios_litewing_battery.h"
#include <assert.h>
#include <math.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
static const char *scenario;
static int creates, adc_inits, publications, delays, reads;
static void (*entry)(void *);
static bool in_worker;
static int64_t now=1000000;
static jmp_buf finished;
static int fail(const char *s) { return strcmp(scenario,s)==0; }
UAVObjHandle FlightBatteryStateHandle(void) { return fail("handle")?NULL:(void *)1; }
int FlightBatteryStateGetMetadata(UAVObjMetadata *m) { m->mode=1; m->telemetryUpdatePeriod=1000; return fail("get-meta")?-1:0; }
void UAVObjSetTelemetryUpdateMode(UAVObjMetadata *m,int mode) { m->mode=mode; }
int FlightBatteryStateSetMetadata(const UAVObjMetadata *m) {
    assert(m->mode==UPDATEMODE_ONCHANGE && m->telemetryUpdatePeriod==0);
    return fail("set-meta")?-1:0;
}
int FlightBatteryStateSet(const FlightBatteryStateData *s) {
    publications++;
    assert(s->NbCells==1 && s->NbCellsAutodetected==0);
    assert(isnan(s->Current) && isnan(s->BoardSupplyVoltage) && isnan(s->PeakCurrent));
    assert(isnan(s->AvgCurrent) && isnan(s->ConsumedEnergy) && isnan(s->EstimatedFlightTime));
    if(!in_worker || fail("adc-init") || fail("read") || fail("stale") ||
       (fail("runtime-publish") && publications>=3)) assert(isnan(s->Voltage));
    else assert(fabsf(s->Voltage-3.9f)<0.0001f);
    return fail("initial-publish") || (fail("runtime-publish") && publications==2) ? -1 : 0;
}
int xTaskCreatePinnedToCore(void (*f)(void *),const char *name,unsigned stack,void *arg,
                          unsigned priority,void *handle,int core) {
    assert(name && stack>=3072 && priority==1 && !arg && !handle && core==0);
    creates++; entry=f; return fail("create")?0:pdPASS;
}
int PIOS_LiteWing_BatteryADC_Init(void) { assert(in_worker); adc_inits++; return fail("adc-init")?-1:0; }
bool PIOS_LiteWing_BatteryADC_Read(struct litewing_battery_sample *s) {
    assert(in_worker && adc_inits==1 && !fail("adc-init"));
    reads++;
    *s=(struct litewing_battery_sample){.valid=!fail("read"),.millivolts=3900,
                                      .captured_us=fail("stale")?0:now-16000};
    return s->valid;
}
int64_t esp_timer_get_time(void) { return now; }
void vTaskDelay(unsigned ticks) {
    assert(ticks==100); now+=100000; if(++delays==2) longjmp(finished,1);
}
int main(int argc,char **argv) {
    assert(argc==2); scenario=argv[1];
    assert(LiteWingBatteryStart()!=0 && creates==0 && adc_inits==0);
    int rc=LiteWingBatteryInitialize();
    bool bad=fail("handle")||fail("get-meta")||fail("set-meta")||fail("initial-publish");
    assert((rc!=0)==bad && adc_inits==0);
    assert(LiteWingBatteryInitialize()!=0);
    if(bad) assert(LiteWingBatteryStart()!=0 && creates==0);
    else {
        assert((LiteWingBatteryStart()==0)==!fail("create"));
        assert(creates==1 && adc_inits==0);
        assert(LiteWingBatteryStart()!=0 && creates==1);
        if(!fail("create")) {
            if(!setjmp(finished)) { in_worker=true; entry(NULL); assert(false); }
            assert(adc_inits==1 && publications==3 && delays==2);
            if(fail("runtime-publish")) assert(reads==1);
        }
    }
    puts("PASS"); return 0;
}
