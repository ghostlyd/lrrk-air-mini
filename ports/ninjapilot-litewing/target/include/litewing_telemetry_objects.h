#pragma once
#include <stddef.h>
#include "uavobjectmanager.h"

/* Trusted registered handles only, never wire-supplied pointers. Zero-wait
 * object-manager mutex acquisition, then one bounded single-instance copy.
 * Accepts only the four non-battery telemetry schemas. Battery must use the
 * age-aware exporter. Failure leaves output untouched. Buffers do not overlap
 * object storage. Task context only, never stabilization/PWM callbacks.
 */
int32_t lw_telemetry_try_pack(UAVObjHandle object, uint8_t *data, size_t capacity);
