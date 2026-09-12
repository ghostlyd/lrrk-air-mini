#include "openpilot.h"
#include "litewing_attitude_trace_module.h"
#include "pios_litewing_brushed_pwm.h"
#include "litewingattitudetrace.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static uint64_t clock_us;
static bool available;
static struct litewing_pwm_observation pwm;
uint32_t UAVObjGetID(UAVObjHandle h) { return (uint32_t)(uintptr_t)h; }
uint16_t UAVObjGetNumBytes(UAVObjHandle h) { (void)h; return 210; }
unsigned UAVObjGetGcsAccess(const UAVObjMetadata *m) { return m->access; }
int64_t esp_timer_get_time(void) { return clock_us; }
bool PIOS_LiteWing_BrushedPWM_GetObservation(struct litewing_pwm_observation *o)
{ if (!available) return false; *o=pwm; return true; }
int32_t LiteWingAttitudeTraceInitialize(void) { return 0; }
UAVObjHandle LiteWingAttitudeTraceHandle(void) { return (void *)(uintptr_t)0xE7AF695A; }
int LiteWingAttitudeTraceGetMetadata(UAVObjMetadata *m) { m->access=ACCESS_READONLY; return 0; }
int main(void)
{
    assert(LiteWingTraceInitialize() == 0);
    assert(LiteWingTraceInitialize() == -1);
    uint8_t wire[210];
    memset(wire, 0xff, sizeof wire);
    UAVObjHandle obj = LiteWingAttitudeTraceHandle();
    assert(LiteWingAttitudeTracePack(obj, 0, wire) == 0);
    assert(wire[160] == 3 && wire[161] == 1 && wire[152] == 0);
    float a[3]={1,2,3}, g[3]={4,5,6}, c[3]={7,8,9}, r[3]={10,11,12};
    struct lw_raw_batch raw={.consumed=1,.retained=1,.first_sequence=55,.last_sequence=55,
        .samples={{.sequence=55,.start_us=1999900,.end_us=1999950,.bytes={0x80,0xff}}}};
    for (unsigned i=0; i<1448; ++i) {
        clock_us=UINT64_C(0x100000000)+2000*i;
        available = i==1000;
        pwm.known_mask=15; pwm.submitted[0]=47; pwm.requested[0]=23; pwm.commits=99;
        LiteWingAttitudeTraceRecord(.002f,a,g,c,r,g,a,&raw);
    }
    assert(LiteWingAttitudeTracePack(obj, 64, wire) == 0);
    LiteWingAttitudeTraceData d;
    memcpy(&d,wire,sizeof d);
    assert(d.RawConsumed==1 && d.RawRetained==1 && d.RawFlags==0);
    assert(d.RawFirst==55 && d.RawLast==55 && d.RawSequence[0]==55);
    assert(d.RawStart[0]==1999900 && d.RawEnd[0]==1999950);
    assert(d.RawBytes[0]==0x80 && d.RawBytes[1]==0xff && d.RawBytes[14]==0);
    assert(d.TimeHigh == 1 && d.TimeLow == 2000000 && d.Sequence == 1000);
    assert(d.Count == 512 && d.TriggerIndex == 64 && d.RecordIndex == 64 && d.State == 3);
    assert(d.PwmAvailable == 1 && d.KnownMask == 15 && d.Submitted[0] == 47);
    assert(d.Accel[2] == 3 && d.Gyro[0] == 4 && d.Corrected[1] == 8 && d.RPY[2] == 12);
    assert(d.PreBias[0] == 4 && d.PreBias[2] == 6);
    assert(d.AppliedBias[0] == 1 && d.AppliedBias[2] == 3);
    assert(LiteWingAttitudeTracePack(obj, 0, wire) == 0);
    memcpy(&d,wire,sizeof d);
    assert(d.Sequence == 936 && d.PwmAvailable == 0 && d.KnownMask == 0);
    assert(LiteWingAttitudeTracePack(obj, 511, wire) == 0);
    uint8_t saved[sizeof wire]; memcpy(saved,wire,sizeof saved);
    LiteWingAttitudeTraceRecord(.5f,a,g,c,r,g,a,&raw);
    assert(LiteWingAttitudeTracePack(obj, 511, wire) == 0 && !memcmp(saved,wire,sizeof saved));
    assert(LiteWingAttitudeTracePack(obj, 512, wire) == -1);
    assert(LiteWingAttitudeTracePack(obj, 65535, wire) == -1);
    assert(LiteWingAttitudeTracePack(obj, 0, NULL) == -1);
    assert(LiteWingAttitudeTracePack(NULL, 0, wire) == -1);
    assert(LiteWingAttitudeTracePack((void *)1, 0, wire) == -1);
    return 0;
}
