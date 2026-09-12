#include "pwm_sdk.h"
#include "litewingpwmobservation.h"
#include "litewing_pwm_observation.h"
#include "litewing_battery_pack.h"
int32_t LiteWingImuTimingPack(UAVObjHandle o,uint16_t i,uint8_t *d) {
    (void)o;(void)i;(void)d;return -1;
}
#include "pios_litewing_brushed_pwm.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "unpack.inc"
static const char *scenario;
static bool available = true;
static unsigned reads;
static int64_t now = 200000;
static uint16_t size = 36;
static struct litewing_pwm_observation snapshot;
static void emit_wire(const uint8_t *wire) {
    printf("WIRE=");
    for (unsigned i=0; i<36; ++i) printf("%02x", wire[i]);
    putchar('\n');
}
static unsigned ordinary_packs, imu_packs;
int32_t UAVObjPack(UAVObjHandle obj, uint16_t instance, uint8_t *data) {
    (void)obj; (void)instance; (void)data; ++ordinary_packs; return 71;
}
int32_t LiteWingImuHealthPack(UAVObjHandle obj, uint16_t instance, uint8_t *data) {
    (void)obj; (void)instance; (void)data; ++imu_packs; return 72;
}
uint32_t UAVObjGetID(UAVObjHandle obj) { return (uint32_t)(uintptr_t)obj; }
uint16_t UAVObjGetNumBytes(UAVObjHandle obj) { (void)obj; return size; }
int64_t esp_timer_get_time(void) { return now; }
bool PIOS_LiteWing_BrushedPWM_GetObservation(struct litewing_pwm_observation *out) {
    ++reads; if (!available) return false; *out = snapshot; return true;
}
int32_t LiteWingPWMObservationInitialize(void) { return !strcmp(scenario,"register") ? -1 : 0; }
UAVObjHandle LiteWingPWMObservationHandle(void) {
    return !strcmp(scenario,"handle") ? NULL : (void *)(uintptr_t)LITEWINGPWMOBSERVATION_OBJID;
}
int LiteWingPWMObservationGetMetadata(UAVObjMetadata *out) {
    out->access = !strcmp(scenario,"access") ? 0 : ACCESS_READONLY;
    return !strcmp(scenario,"metadata") ? -1 : 0;
}
unsigned UAVObjGetGcsAccess(const UAVObjMetadata *m) { return m->access; }
int main(int argc, char **argv) {
    (void)argc; scenario = argv[1];
    assert(LiteWingPwmObservationInitialize() == (!strcmp(scenario,"normal") ? 0 : -1));
    assert(LiteWingPwmObservationInitialize() == -1);
    if (strcmp(scenario,"normal")) return 0;
    UAVObjHandle obj = (void *)(uintptr_t)LITEWINGPWMOBSERVATION_OBJID;
    uint8_t guarded[38]; memset(guarded, 0xa5, sizeof guarded);
    uint8_t *wire = guarded + 1;
    available = false;
    assert(LiteWingPwmObservationPack(obj,0,wire)==0);
    LiteWingPWMObservationData defaults; schema_defaults(&defaults);
    _Static_assert(sizeof(defaults)==36, "wire size");
    _Static_assert(offsetof(LiteWingPWMObservationData,Requested)==16,"requested offset");
    _Static_assert(offsetof(LiteWingPWMObservationData,Version)==32,"version offset");
    assert(memcmp(wire,&defaults,36)==0);
    emit_wire(wire);
    available = true;
    snapshot = (struct litewing_pwm_observation){
        .requested={1,256,1000,0}, .submitted={2,512,2047,0},
        .commits=0x12345678, .write_errors=UINT32_MAX, .stop_errors=3,
        .known_mask=15,.suppression=0x3f,.observed_us=199000};
    struct litewing_pwm_observation before=snapshot;
    assert(LiteWingPwmObservationPack(obj,0,wire)==0);
    const uint8_t expected[36]={1,0,0,0,0x78,0x56,0x34,0x12,255,255,255,255,3,0,0,0,
        1,0,0,1,0xe8,3,0,0,2,0,0,2,255,7,0,0,1,1,15,0x3f};
    assert(memcmp(wire,expected,36)==0);
    emit_wire(wire);
    assert(LiteWingBatteryPack(obj,0,wire)==0 && !memcmp(wire,expected,36));
    assert(ordinary_packs==0 && imu_packs==0);
    assert(LiteWingBatteryPack((void *)(uintptr_t)0xDA60A0C6,0,wire)==72 && imu_packs==1);
    assert(LiteWingBatteryPack((void *)(uintptr_t)0x12345678,0,wire)==71 && ordinary_packs==1);
    available=false;
    assert(LiteWingBatteryPack(obj,0,wire)==0 && !memcmp(wire,&defaults,36));
    assert(ordinary_packs==1); /* contention never reaches the cached packer */
    available=true;
    assert(memcmp(&snapshot,&before,sizeof snapshot)==0);
    snapshot.known_mask=5;
    assert(LiteWingPwmObservationPack(obj,0,wire)==0 && wire[34]==5);
    assert(wire[26]==0 && wire[27]==0); /* unknown channel is cleared */
    emit_wire(wire);
    now=snapshot.observed_us+LITEWING_PWM_OBSERVATION_MAX_AGE_US;
    assert(LiteWingPwmObservationPack(obj,0,wire)==0 && wire[33]==0 && wire[34]==0);
    emit_wire(wire);
    now=INT64_MAX;
    assert(LiteWingPwmObservationPack(obj,0,wire)==0 && wire[33]==0 && wire[34]==0);
    now=-1;
    assert(LiteWingPwmObservationPack(obj,0,wire)==0 && !memcmp(wire,&defaults,36));
    now=0;
    assert(LiteWingPwmObservationPack(obj,0,wire)==0 && wire[33]==0);
    snapshot.observed_us=-1;
    assert(LiteWingPwmObservationPack(obj,0,wire)==0 && wire[33]==0);
    unsigned previous=reads;
    assert(LiteWingPwmObservationPack(obj,1,wire)==-1);
    assert(LiteWingPwmObservationPack(obj,0,NULL)==-1);
    assert(LiteWingPwmObservationPack(NULL,0,wire)==-1);
    size=35; assert(LiteWingPwmObservationPack(obj,0,wire)==-1);
    assert(reads==previous && guarded[0]==0xa5 && guarded[37]==0xa5);
    assert(UAVObjUnpack(obj,0,wire)==-1);
    assert(UAVObjUnpack((void *)(uintptr_t)(LITEWINGPWMOBSERVATION_OBJID+1),0,wire)==-1);
    assert(UAVObjUnpack((void *)(uintptr_t)0xDA60A0C6,0,wire)==-1);
    assert(UAVObjUnpack((void *)(uintptr_t)0x26962352,0,wire)==123);
    puts("PWM_WIRE_ACCESS_SNAPSHOT=PASS");
}
