/* Task-context snapshots only; no object mutation or freshness synthesis. */
#include "openpilot.h"
#include "litewing_telemetry_read.h"
#include "litewing_telemetry_objects.h"
#include "litewing_battery_pack.h"
#include "attitudestate.h"
#include "flightstatus.h"
#include "flightbatterystate.h"
#include "systemalarms.h"
#include "actuatorcommand.h"
#include "esp_timer.h"
#include <string.h>

#define PIN(name, id, size) \
    _Static_assert(name##_OBJID == UINT32_C(id) && name##_NUMBYTES == size, "telemetry schema drift")
PIN(ATTITUDESTATE, 0xD7E0D964, 28);
PIN(FLIGHTSTATUS, 0xEF69B6BC, 8);
PIN(FLIGHTBATTERYSTATE, 0x26962352, 30);
PIN(SYSTEMALARMS, 0x6B7639EC, 25);
PIN(ACTUATORCOMMAND, 0xB8229FE4, 29);
#undef PIN

int lw_telemetry_read(unsigned index, struct lw_telemetry_record *out)
{
    if (!out) return -1;
    memset(out, 0, sizeof(*out));
    static const uint32_t ids[] = {ATTITUDESTATE_OBJID, FLIGHTSTATUS_OBJID,
        FLIGHTBATTERYSTATE_OBJID, SYSTEMALARMS_OBJID, ACTUATORCOMMAND_OBJID};
    static const uint16_t sizes[] = {28,8,30,25,29};
    if (index >= 5) return -1;
    struct lw_telemetry_record record = {.object_id=ids[index], .data_len=sizes[index],
        .sample_age_us=UINT64_MAX};
    int64_t serialized = -1;
    if (index == 2) {
        if (LiteWingBatterySnapshot(record.data, sizeof(record.data),
            &serialized, &record.sample_age_us)) return -1;
    } else {
        /* Generated Handle getters return immutable registered pointers;
         * the actual copy is exclusively through the zero-wait guard. */
        UAVObjHandle object = NULL;
        switch (index) {
        case 0: object=AttitudeStateHandle(); break;
        case 1: object=FlightStatusHandle(); break;
        case 3: object=SystemAlarmsHandle(); break;
        case 4: object=ActuatorCommandHandle(); break;
        }
        if (!object || lw_telemetry_try_pack(object, record.data, sizeof(record.data))) return -1;
        serialized = esp_timer_get_time();
    }
    if (serialized < 0) return -1;
    record.serialized_us = (uint64_t)serialized;
    *out = record;
    return 0;
}
