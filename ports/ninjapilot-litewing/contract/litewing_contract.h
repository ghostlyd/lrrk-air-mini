#ifndef LRRK_LITEWING_CONTRACT_H
#define LRRK_LITEWING_CONTRACT_H

#include <stdbool.h>
#include <stdint.h>

#define LITEWING_BOARD_TYPE 0x13u
#define LITEWING_BOARD_REVISION 0x02u
#define LITEWING_OUTPUT_CHANNELS 4u
#define LITEWING_ACTUATOR_MIN 0u
#define LITEWING_ACTUATOR_MAX 1000u
#define LITEWING_PWM_HZ 20000u
#define LITEWING_IMU_SDA_GPIO 11u
#define LITEWING_IMU_SCL_GPIO 10u
#define LITEWING_IMU_INT_GPIO 12u
#define LITEWING_MOTOR_GPIO_1 5u
#define LITEWING_MOTOR_GPIO_2 6u
#define LITEWING_MOTOR_GPIO_3 3u
#define LITEWING_MOTOR_GPIO_4 4u
#define LITEWING_MPU6050_I2C_ADDRESS 0x68u
#define LITEWING_MPU6050_WHO_AM_I 0x68u
#define LITEWING_MPU6050_SAMPLE_RATE_HZ 500u
#define LITEWING_MPU6050_DLPF_CFG 0x03u
#define LITEWING_MPU6050_SAMPLE_DIVIDER 0x01u
#define LITEWING_MPU6050_GYRO_CONFIG 0x18u
#define LITEWING_MPU6050_ACCEL_CONFIG 0x00u

struct litewing_output_frame {
    uint16_t duty[LITEWING_OUTPUT_CHANNELS];
};

struct litewing_output_state {
    bool hardware_ready;
    bool imu_healthy;
    bool link_fresh;
    bool armed;
    bool failsafe;
    bool shutdown;
};

uint16_t litewing_clamp_duty(int32_t value);
bool litewing_mpu6050_identity_valid(uint8_t who_am_i);
bool litewing_arm_allowed(bool imu_present, bool imu_healthy, bool link_fresh, bool disarmed);
bool litewing_output_allowed(const struct litewing_output_state *state);
void litewing_sanitize_frame(const struct litewing_output_frame *requested,
                             const struct litewing_output_state *state,
                             struct litewing_output_frame *sanitized);
void litewing_safe_frame(struct litewing_output_frame *frame);

#endif
