#ifndef LRRK_PIOS_LITEWING_MPU6050_H
#define LRRK_PIOS_LITEWING_MPU6050_H

#include <stdbool.h>
#include <stdint.h>
#include "litewing_imu_health.h"

#define LITEWING_MPU6050_STALE_TIMEOUT_MS 20u

/* Coherent primitive snapshot; no peripheral or object operations under lock.
 * The timed form additionally returns monotonic sample time for telemetry,
 * which must not reuse the native exporter's single-cycle uint32 age alone.
 */
void PIOS_LiteWing_MPU6050_GetObservation(struct lw_imu_observation *out);
void PIOS_LiteWing_MPU6050_GetTiming(struct lw_imu_timing *out);
void PIOS_LiteWing_MPU6050_GetTimedObservation(struct lw_imu_observation *out,
                                              int64_t *sample_us);

int32_t PIOS_LiteWing_MPU6050_Init(uint32_t i2c_id, uint8_t address);
bool PIOS_LiteWing_MPU6050_IsHealthy(void);
void PIOS_LiteWing_MPU6050_Shutdown(void);

#endif /* LRRK_PIOS_LITEWING_MPU6050_H */
