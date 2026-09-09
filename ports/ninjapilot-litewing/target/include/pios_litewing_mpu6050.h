#ifndef LRRK_PIOS_LITEWING_MPU6050_H
#define LRRK_PIOS_LITEWING_MPU6050_H

#include <stdbool.h>
#include <stdint.h>

int32_t PIOS_LiteWing_MPU6050_Init(uint32_t i2c_id, uint8_t address);
bool PIOS_LiteWing_MPU6050_IsHealthy(void);
void PIOS_LiteWing_MPU6050_Shutdown(void);

#endif /* LRRK_PIOS_LITEWING_MPU6050_H */
