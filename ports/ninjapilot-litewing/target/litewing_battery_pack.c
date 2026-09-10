/* Target-only packing boundary: cached UAVObjects never renew voltage age. */
#include "openpilot.h"
#include "litewing_battery_pack.h"
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
    if (UAVObjGetID(obj) != UINT32_C(0x26962352))
        return UAVObjPack(obj, instance, data);
    /* Pinned FlightBatteryState wire schema: seven float32s and two bytes.
     * Never fall back to storage on an unexpected schema or instance.
     */
    if (!data || instance != 0 || UAVObjGetNumBytes(obj) != 30) return -1;
    struct litewing_battery_sample sample;
    portENTER_CRITICAL(&sample_lock);
    sample = latest;
    portEXIT_CRITICAL(&sample_lock);
    float values[7];
    litewing_battery_export(&sample, esp_timer_get_time(), values);
    _Static_assert(sizeof(values) == 28, "requires float32 wire representation");
    /* ESP32-S3 is little-endian, matching the pinned UAVObject serializer. */
    memcpy(data, values, sizeof(values));
    data[28] = 1;
    data[29] = 0;
    return 0;
}
