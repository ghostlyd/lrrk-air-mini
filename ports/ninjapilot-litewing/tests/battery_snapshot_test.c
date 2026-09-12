#include "litewing_battery_pack.h"
int32_t LiteWingImuTimingPack(UAVObjHandle o,uint16_t i,uint8_t *d) {
    (void)o;(void)i;(void)d;return -1;
}
int32_t LiteWingPwmObservationPack(UAVObjHandle obj, uint16_t instance, uint8_t *data) {
    (void)obj; (void)instance; (void)data; return -1;
}
#include <assert.h>
int32_t LiteWingImuHealthPack(UAVObjHandle obj,uint16_t inst,uint8_t *data) {
    (void)obj; (void)inst; (void)data; assert(false); return -1;
}
#include <math.h>
#include <string.h>

static int64_t now = 1100;
static int replace_sample;
static uint32_t object_id = UINT32_C(0x26962352);
static uint16_t object_size = 30;
uint32_t UAVObjGetID(UAVObjHandle obj) { (void)obj; return object_id; }
uint16_t UAVObjGetNumBytes(UAVObjHandle obj) { (void)obj; return object_size; }
int32_t UAVObjPack(UAVObjHandle obj, uint16_t instance, uint8_t *data)
{ (void)obj; (void)instance; (void)data; assert(0); return -1; }
int64_t esp_timer_get_time(void)
{
    if (replace_sample) {
        const struct litewing_battery_sample next = {.valid=true, .millivolts=4100, .captured_us=1090};
        LiteWingBatteryStoreSample(&next);
        replace_sample = 0;
    }
    return now;
}
static void check(const uint8_t *wire, float voltage)
{
    float values[7];
    memcpy(values, wire, 28);
    if (isnan(voltage)) assert(isnan(values[0]));
    else assert(fabsf(values[0]-voltage) < 0.00001f);
    for (unsigned i=1; i<7; ++i) assert(isnan(values[i]));
    assert(wire[28] == 1 && wire[29] == 0);
}
int main(void)
{
    uint8_t wire[32]; int64_t serialized; uint64_t age;
    assert(LiteWingBatterySnapshot(wire,30,&serialized,&age)==0);
    check(wire,NAN); assert(age==UINT64_MAX && serialized==now);
    struct litewing_battery_sample sample = {.valid=true, .millivolts=3800, .captured_us=1000};
    LiteWingBatteryStoreSample(&sample);
    replace_sample=1;
    assert(LiteWingBatterySnapshot(wire,30,&serialized,&age)==0);
    check(wire,3.8f); assert(age==100 && serialized==1100);
    now=1110;
    assert(LiteWingBatterySnapshot(wire,30,&serialized,&age)==0);
    check(wire,4.1f); assert(age==20 && serialized==1110);
    assert(LiteWingBatteryPack((void *)1,0,wire)==0); check(wire,4.1f);
    now=501090;
    assert(LiteWingBatterySnapshot(wire,30,&serialized,&age)==0);
    check(wire,4.1f); assert(age==500000);
    ++now;
    assert(LiteWingBatterySnapshot(wire,30,&serialized,&age)==0);
    check(wire,NAN); assert(age==UINT64_MAX);
    now=1089;
    assert(LiteWingBatterySnapshot(wire,30,&serialized,&age)==0);
    check(wire,NAN); assert(age==UINT64_MAX);
    now=-1; memset(wire,0xa5,sizeof(wire));
    assert(LiteWingBatterySnapshot(wire,30,&serialized,&age)==-1);
    for(size_t i=0;i<sizeof(wire);++i) assert(wire[i]==0xa5);
    assert(serialized==-1 && age==UINT64_MAX);
    now=1110;
    for(size_t capacity=0;capacity<30;++capacity) {
        assert(LiteWingBatterySnapshot(wire,capacity,&serialized,&age)==-1);
        assert(serialized==-1 && age==UINT64_MAX);
        for(size_t i=0;i<sizeof(wire);++i) assert(wire[i]==0xa5);
    }
    assert(LiteWingBatterySnapshot(NULL,30,&serialized,&age)==-1);
    assert(LiteWingBatterySnapshot(wire,30,NULL,&age)==-1);
    assert(LiteWingBatterySnapshot(wire,30,&serialized,NULL)==-1);
    for(size_t i=0;i<sizeof(wire);++i) assert(wire[i]==0xa5);
    assert(LiteWingBatteryPack((void *)1,1,wire)==-1);
    object_size=29; assert(LiteWingBatteryPack((void *)1,0,wire)==-1);
    return 0;
}
