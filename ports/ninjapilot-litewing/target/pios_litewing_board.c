/*
 * LiteWing board bring-up seam.
 *
 * The external NinjaPilot board file calls this once, before flight modules
 * start. It deliberately initializes the brushed backend before the sensor:
 * every failure path therefore has already-established zero outputs.
 */
#include "pios.h"
#include <stdio.h>

#include <pios_esp32_priv.h>

#include "litewing_contract.h"
#include "pios_litewing_brushed_pwm.h"
#include "pios_litewing_mpu6050.h"

static uint32_t litewing_i2c_id;

static const struct pios_esp32_i2c_cfg litewing_imu_i2c_cfg = {
    .port = I2C_NUM_0,
    .sda_pin = LITEWING_IMU_SDA_GPIO,
    .scl_pin = LITEWING_IMU_SCL_GPIO,
    .speed_hz = 400000u,
};

int32_t PIOS_LiteWing_Board_Init(void)
{
    if (PIOS_LiteWing_BrushedPWM_Init() != 0) {
        return -1;
    }

    if (PIOS_ESP32_I2C_Init(&litewing_i2c_id, &litewing_imu_i2c_cfg) != 0) {
        PIOS_LiteWing_BrushedPWM_SetFailsafe(true);
        return -2;
    }

    const int32_t imu_result = PIOS_LiteWing_MPU6050_Init(litewing_i2c_id,
                                   LITEWING_MPU6050_I2C_ADDRESS);
    if (imu_result != 0) {
        printf("[LiteWing] MPU6050 initialization result %ld\n", (long)imu_result);
        PIOS_LiteWing_BrushedPWM_SetFailsafe(true);
        return -3;
    }

    return 0;
}

void PIOS_LiteWing_Board_Shutdown(void)
{
    PIOS_LiteWing_MPU6050_Shutdown();
    PIOS_LiteWing_BrushedPWM_Shutdown();
}
