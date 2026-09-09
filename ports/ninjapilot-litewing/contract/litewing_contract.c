#include "litewing_contract.h"

uint16_t litewing_clamp_duty(int32_t value)
{
    if (value <= (int32_t)LITEWING_ACTUATOR_MIN) {
        return LITEWING_ACTUATOR_MIN;
    }
    if (value >= (int32_t)LITEWING_ACTUATOR_MAX) {
        return LITEWING_ACTUATOR_MAX;
    }
    return (uint16_t)value;
}

bool litewing_mpu6050_identity_valid(uint8_t who_am_i)
{
    return who_am_i == 0x68u;
}

bool litewing_arm_allowed(bool imu_present, bool imu_healthy, bool link_fresh, bool disarmed)
{
    return imu_present && imu_healthy && link_fresh && disarmed;
}

void litewing_safe_frame(struct litewing_output_frame *frame)
{
    if (frame == 0) {
        return;
    }
    for (uint32_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        frame->duty[index] = LITEWING_ACTUATOR_MIN;
    }
}
