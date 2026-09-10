#pragma once
#include "uavobjectmanager.h"
#include "litewing_battery_voltage.h"

/* Worker-only publication; readers obtain one coherent acquisition record. */
void LiteWingBatteryStoreSample(const struct litewing_battery_sample *sample);
int32_t LiteWingBatteryPack(UAVObjHandle obj, uint16_t instance, uint8_t *data);
/* Coherent voltage bytes and age, without a cached-object read. Serialized time
 * is the exporter clock; known age applies to the measured voltage only.
 * Unmeasured/stale/future samples produce NaN and UINT64_MAX age. Negative
 * exporter clock is an error. Failure leaves data untouched, timestamp -1 and
 * age UINT64_MAX where pointers exist. Caller buffers/pointers do not overlap.
 */
int32_t LiteWingBatterySnapshot(uint8_t *data, size_t capacity,
                               int64_t *serialized_us, uint64_t *sample_age_us);
