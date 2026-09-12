#ifndef LRRK_ATTITUDE_TRACE_MODULE_H
#define LRRK_ATTITUDE_TRACE_MODULE_H
#ifdef ESP_PLATFORM
#include "sdkconfig.h"
#endif
#if CONFIG_LRRK_ATTITUDE_TRACE
#include "openpilot.h"
#include "uavobjectmanager.h"
int32_t LiteWingTraceInitialize(void);
int32_t LiteWingAttitudeTracePack(UAVObjHandle, uint16_t, uint8_t *);
void LiteWingAttitudeTraceRecord(float dt, const float accel[3], const float gyro[3],
                                const float corrected[3], const float rpy[3],
                                const float pre_bias[3], const float applied_bias[3]);
#else
#define LiteWingAttitudeTraceRecord(...) ((void)0)
#endif
#endif
