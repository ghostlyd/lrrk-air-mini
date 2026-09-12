/* Target-only packing boundary: cached UAVObjects never renew voltage age. */
#include "openpilot.h"
#include "litewing_battery_pack.h"
#include "litewing_imu_health_pack.h"
#include "litewing_pwm_observation.h"
#include "litewing_attitude_trace_module.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include <string.h>

static portMUX_TYPE sample_lock = portMUX_INITIALIZER_UNLOCKED;
static struct litewing_battery_sample latest;

void LiteWingBatteryStoreSample(const struct litewing_battery_sample *sample)
{
    portENTER_CRITICAL(&sample_lock);
    latest = *sample;
    portEXIT_CRITICAL(&sample_lock);
}

int32_t LiteWingBatteryPack(UAVObjHandle obj, uint16_t instance, uint8_t *data)
{
    if (obj && UAVObjGetID(obj) == UINT32_C(0x5AF673A8))
        return LiteWingImuTimingPack(obj, instance, data);
#if CONFIG_LRRK_ATTITUDE_TRACE
    if (obj && UAVObjGetID(obj) == UINT32_C(0xE7AF695A))
        return LiteWingAttitudeTracePack(obj, instance, data);
#endif
    if (UAVObjGetID(obj) == UINT32_C(0xA6453F6E))
        return LiteWingPwmObservationPack(obj, instance, data);
    if (UAVObjGetID(obj) == UINT32_C(0xDA60A0C6))
        return LiteWingImuHealthPack(obj, instance, data);
    if (UAVObjGetID(obj) != UINT32_C(0x26962352))
        return UAVObjPack(obj, instance, data);
    /* Pinned FlightBatteryState wire schema: seven float32s and two bytes.
     * Never fall back to storage on an unexpected schema or instance.
     */
    if (!data || instance != 0 || UAVObjGetNumBytes(obj) != 30) return -1;
    int64_t serialized;
    uint64_t age;
    return LiteWingBatterySnapshot(data, 30, &serialized, &age);
}

int32_t LiteWingBatterySnapshot(uint8_t *data, size_t capacity,
                               int64_t *serialized_us, uint64_t *sample_age_us)
{
    if (serialized_us) *serialized_us = -1;
    if (sample_age_us) *sample_age_us = UINT64_MAX;
    if (!data || capacity < 30 || !serialized_us || !sample_age_us) return -1;
    struct litewing_battery_sample sample;
    portENTER_CRITICAL(&sample_lock);
    sample = latest;
    portEXIT_CRITICAL(&sample_lock);
    int64_t now = esp_timer_get_time();
    if (now < 0) return -1;
    float values[7];
    litewing_battery_export(&sample, now, values);
    _Static_assert(sizeof(values) == 28, "requires float32 wire representation");
    /* ESP32-S3 is little-endian, matching the pinned UAVObject serializer. */
    memcpy(data, values, sizeof(values));
    data[28] = 1;
    data[29] = 0;
    uint32_t millivolts;
    if (litewing_battery_read(&sample, now, &millivolts))
        *sample_age_us = (uint64_t)(now - sample.captured_us);
    *serialized_us = now;
    return 0;
}
