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
    return who_am_i == LITEWING_MPU6050_WHO_AM_I;
}

bool litewing_mpu6050_orient_top_0deg(const int16_t sensor[3], int16_t body[3])
{
    if (sensor == 0 || body == 0) {
        return false;
    }
    /* Match NinjaPilot's MPU6000 TOP_0DEG body convention exactly. The
     * -1-z expression is defined for every int16 input without signed
     * overflow, including INT16_MIN. */
    body[0] = sensor[1];
    body[1] = sensor[0];
    body[2] = (int16_t)(-1 - sensor[2]);
    return true;
}

bool litewing_arm_allowed(bool imu_present, bool imu_healthy, bool link_fresh, bool disarmed)
{
    return imu_present && imu_healthy && link_fresh && disarmed;
}

bool litewing_output_allowed(const struct litewing_output_state *state)
{
    return state != 0 && state->hardware_ready && state->imu_healthy &&
           state->link_fresh && state->armed && !state->failsafe &&
           !state->shutdown;
}

void litewing_sanitize_frame(const struct litewing_output_frame *requested,
                             const struct litewing_output_state *state,
                             struct litewing_output_frame *sanitized)
{
    if (sanitized == 0) {
        return;
    }
    if (requested == 0 || !litewing_output_allowed(state)) {
        litewing_safe_frame(sanitized);
        return;
    }
    for (uint32_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        sanitized->duty[index] = litewing_clamp_duty(requested->duty[index]);
    }
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
