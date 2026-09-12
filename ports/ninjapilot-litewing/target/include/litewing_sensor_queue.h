#ifndef LITEWING_SENSOR_QUEUE_H
#define LITEWING_SENSOR_QUEUE_H
#ifdef ESP_PLATFORM
#include "sdkconfig.h"
#endif
#include "litewing_raw_provenance.h"
/* Expand only where the PIOS sensor types are available. */
#define LW_SENSOR_PAYLOAD_SIZE (sizeof(PIOS_SENSORS_3Axis_SensorsWithTemp) + 2u * sizeof(Vector3i16))
#if CONFIG_LRRK_ATTITUDE_TRACE
#define LW_SENSOR_QUEUE_SIZE (LW_SENSOR_PAYLOAD_SIZE + sizeof(struct lw_raw_sample))
#else
#define LW_SENSOR_QUEUE_SIZE LW_SENSOR_PAYLOAD_SIZE
#endif
#endif
