#include "litewing_telemetry_read.h"
#include "litewing_telemetry_objects.h"
#include "litewing_battery_pack.h"
#include <assert.h>
#include <string.h>

static unsigned selected, packs, batteries;
static int fail, missing;
static int64_t now = 1234;
static uint8_t handles[5];
UAVObjHandle AttitudeStateHandle(void) { return missing ? NULL : &handles[0]; }
UAVObjHandle FlightStatusHandle(void) { return &handles[1]; }
UAVObjHandle FlightBatteryStateHandle(void) { assert(0); return NULL; }
UAVObjHandle SystemAlarmsHandle(void) { return &handles[3]; }
UAVObjHandle ActuatorCommandHandle(void) { return &handles[4]; }
int64_t esp_timer_get_time(void) { return now; }
int32_t lw_telemetry_try_pack(UAVObjHandle object, uint8_t *data, size_t capacity) {
    assert(object == &handles[selected] && capacity >= 29 && selected != 2);
    ++packs;
    memset(data, 0xa5, 29);
    return fail ? -1 : 0;
}
int32_t LiteWingBatterySnapshot(uint8_t *data, size_t capacity,
                               int64_t *serialized, uint64_t *age) {
    assert(selected == 2 && capacity >= 30);
    ++batteries; memset(data, 0xb6, 30);
    *serialized = now; *age = 12;
    return fail ? -1 : 0;
}
static void zero(const void *value, size_t size) {
    const uint8_t *p = value;
    for (size_t i=0;i<size;++i) assert(p[i] == 0);
}
int main(void) {
    static const uint32_t ids[] = {0xD7E0D964,0xEF69B6BC,0x26962352,0x6B7639EC,0xB8229FE4};
    static const uint16_t sizes[] = {28,8,30,25,29};
    struct lw_telemetry_record record;
    for (selected=0;selected<5;++selected) {
        assert(lw_telemetry_read(selected,&record)==0);
        assert(record.object_id==ids[selected] && record.data_len==sizes[selected]);
        assert(record.serialized_us==1234);
        assert(record.sample_age_us==(selected==2 ? 12 : UINT64_MAX));
        assert(record.data[0]==(selected==2 ? 0xb6 : 0xa5));
        fail=1; assert(lw_telemetry_read(selected,&record)==-1); zero(&record,sizeof(record)); fail=0;
    }
    assert(packs==8 && batteries==2);
    assert(lw_telemetry_read(5,&record)==-1); zero(&record,sizeof(record));
    assert(lw_telemetry_read(0,NULL)==-1);
    selected=0; missing=1;
    assert(lw_telemetry_read(0,&record)==-1); zero(&record,sizeof(record)); missing=0;
    now=-1;
    assert(lw_telemetry_read(0,&record)==-1); zero(&record,sizeof(record));
    selected=2;
    assert(lw_telemetry_read(2,&record)==-1); zero(&record,sizeof(record));
    return 0;
}
