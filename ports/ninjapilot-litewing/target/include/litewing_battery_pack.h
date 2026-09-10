#pragma once
#include "uavobjectmanager.h"
#include "litewing_battery_voltage.h"

/* Worker-only publication; readers obtain one coherent acquisition record. */
void LiteWingBatteryStoreSample(const struct litewing_battery_sample *sample);
int32_t LiteWingBatteryPack(UAVObjHandle obj, uint16_t instance, uint8_t *data);
