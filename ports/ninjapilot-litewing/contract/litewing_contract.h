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

enum litewing_motor_corner {
    LITEWING_MOTOR_CORNER_FRONT_RIGHT,
    LITEWING_MOTOR_CORNER_REAR_RIGHT,
    LITEWING_MOTOR_CORNER_REAR_LEFT,
    LITEWING_MOTOR_CORNER_FRONT_LEFT,
};

enum litewing_motor_rotation {
    LITEWING_MOTOR_ROTATION_CW,
    LITEWING_MOTOR_ROTATION_CCW,
};

/* Channel order is PCB J7/J8/J9/J10 and GPIO 5/6/3/4. The A/B corner
 * silkscreen and fitted wire colors establish alternating CW/CCW motors. */
#define LITEWING_MOTOR_1_CORNER LITEWING_MOTOR_CORNER_FRONT_RIGHT
#define LITEWING_MOTOR_2_CORNER LITEWING_MOTOR_CORNER_REAR_RIGHT
#define LITEWING_MOTOR_3_CORNER LITEWING_MOTOR_CORNER_REAR_LEFT
#define LITEWING_MOTOR_4_CORNER LITEWING_MOTOR_CORNER_FRONT_LEFT
#define LITEWING_MOTOR_1_ROTATION LITEWING_MOTOR_ROTATION_CCW
#define LITEWING_MOTOR_2_ROTATION LITEWING_MOTOR_ROTATION_CW
#define LITEWING_MOTOR_3_ROTATION LITEWING_MOTOR_ROTATION_CCW
#define LITEWING_MOTOR_4_ROTATION LITEWING_MOTOR_ROTATION_CW
#define LITEWING_MOTOR_1_MIXER_YAW (-127)
#define LITEWING_MOTOR_2_MIXER_YAW 127
#define LITEWING_MOTOR_3_MIXER_YAW (-127)
#define LITEWING_MOTOR_4_MIXER_YAW 127

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
bool litewing_mpu6050_orient_top_0deg(const int16_t sensor[3], int16_t body[3]);
bool litewing_arm_allowed(bool imu_present, bool imu_healthy, bool link_fresh, bool disarmed);
bool litewing_output_allowed(const struct litewing_output_state *state);
void litewing_sanitize_frame(const struct litewing_output_frame *requested,
                             const struct litewing_output_state *state,
                             struct litewing_output_frame *sanitized);
void litewing_safe_frame(struct litewing_output_frame *frame);

#endif
