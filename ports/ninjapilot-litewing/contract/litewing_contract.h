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

struct litewing_output_frame {
    uint16_t duty[LITEWING_OUTPUT_CHANNELS];
};

uint16_t litewing_clamp_duty(int32_t value);
bool litewing_mpu6050_identity_valid(uint8_t who_am_i);
bool litewing_arm_allowed(bool imu_present, bool imu_healthy, bool link_fresh, bool disarmed);
void litewing_safe_frame(struct litewing_output_frame *frame);

#endif
