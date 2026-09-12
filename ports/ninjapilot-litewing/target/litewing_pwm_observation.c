/* Request-only diagnostics. Never writes driver state or starts a worker. */
#include "openpilot.h"
#include "litewingpwmobservation.h"
#include "litewing_pwm_observation.h"
#include "pios_litewing_brushed_pwm.h"
#include "esp_timer.h"
#include <stddef.h>
#include <string.h>

_Static_assert(sizeof(LiteWingPWMObservationData) == 36, "PWM wire size changed");
_Static_assert(offsetof(LiteWingPWMObservationData, SnapshotAgeMs) == 0, "age offset");
_Static_assert(offsetof(LiteWingPWMObservationData, Commits) == 4, "commits offset");
_Static_assert(offsetof(LiteWingPWMObservationData, WriteErrors) == 8, "write offset");
_Static_assert(offsetof(LiteWingPWMObservationData, StopErrors) == 12, "stop offset");
_Static_assert(offsetof(LiteWingPWMObservationData, Requested) == 16, "requested offset");
_Static_assert(offsetof(LiteWingPWMObservationData, Submitted) == 24, "submitted offset");
_Static_assert(offsetof(LiteWingPWMObservationData, Version) == 32, "version offset");
_Static_assert(offsetof(LiteWingPWMObservationData, Available) == 33, "available offset");
_Static_assert(offsetof(LiteWingPWMObservationData, KnownMask) == 34, "known offset");
_Static_assert(offsetof(LiteWingPWMObservationData, Suppression) == 35, "suppression offset");

static void put16(uint8_t *out, uint16_t value)
{
    out[0] = (uint8_t)value; out[1] = (uint8_t)(value >> 8);
}
static void put32(uint8_t *out, uint32_t value)
{
    put16(out, (uint16_t)value); put16(out + 2, (uint16_t)(value >> 16));
}

int32_t LiteWingPwmObservationPack(UAVObjHandle obj, uint16_t instance, uint8_t *data)
{
    if (!obj || !data || instance != 0 ||
        UAVObjGetID(obj) != LITEWINGPWMOBSERVATION_OBJID || UAVObjGetNumBytes(obj) != 36)
        return -1;
    memset(data, 0, 36);
    put32(data, UINT32_MAX);
    data[32] = 1;
    struct litewing_pwm_observation snapshot = {0};
    /* Exactly one current zero-wait read; never fall back to cached UAVO data. */
    if (!PIOS_LiteWing_BrushedPWM_GetObservation(&snapshot)) return 0;
    int64_t now = esp_timer_get_time();
    if (now < 0 || snapshot.observed_us < 0 || now < snapshot.observed_us) return 0;
    uint64_t age = (uint64_t)(now - snapshot.observed_us);
    uint64_t age_ms = age / 1000;
    put32(data, age_ms >= UINT32_MAX ? UINT32_MAX : (uint32_t)age_ms);
    if (age >= LITEWING_PWM_OBSERVATION_MAX_AGE_US) return 0;
    put32(data + 4, snapshot.commits);
    put32(data + 8, snapshot.write_errors);
    put32(data + 12, snapshot.stop_errors);
    for (unsigned channel = 0; channel < 4; ++channel) {
        put16(data + 16 + channel * 2, snapshot.requested[channel]);
        if (snapshot.known_mask & (1u << channel))
            put16(data + 24 + channel * 2, snapshot.submitted[channel]);
    }
    data[33] = 1;
    data[34] = snapshot.known_mask & 15u;
    data[35] = snapshot.suppression;
    return 0;
}

int32_t LiteWingPwmObservationInitialize(void)
{
    static bool attempted;
    if (attempted) return -1;
    attempted = true;
    if (LiteWingPWMObservationInitialize() != 0 || !LiteWingPWMObservationHandle()) return -1;
    UAVObjMetadata metadata;
    if (LiteWingPWMObservationGetMetadata(&metadata) != 0 ||
        UAVObjGetGcsAccess(&metadata) != ACCESS_READONLY) return -1;
    return 0;
}
