#include <assert.h>
#include <stddef.h>
#include <stdint.h>

#include "litewing_contract.h"

int main(void)
{
    assert(LITEWING_MOTOR_1_CORNER == LITEWING_MOTOR_CORNER_FRONT_RIGHT);
    assert(LITEWING_MOTOR_2_CORNER == LITEWING_MOTOR_CORNER_REAR_RIGHT);
    assert(LITEWING_MOTOR_3_CORNER == LITEWING_MOTOR_CORNER_REAR_LEFT);
    assert(LITEWING_MOTOR_4_CORNER == LITEWING_MOTOR_CORNER_FRONT_LEFT);
    assert(LITEWING_MOTOR_1_ROTATION == LITEWING_MOTOR_ROTATION_CCW);
    assert(LITEWING_MOTOR_2_ROTATION == LITEWING_MOTOR_ROTATION_CW);
    assert(LITEWING_MOTOR_3_ROTATION == LITEWING_MOTOR_ROTATION_CCW);
    assert(LITEWING_MOTOR_4_ROTATION == LITEWING_MOTOR_ROTATION_CW);
    assert(LITEWING_MOTOR_1_MIXER_YAW == -127);
    assert(LITEWING_MOTOR_2_MIXER_YAW == 127);
    assert(LITEWING_MOTOR_3_MIXER_YAW == -127);
    assert(LITEWING_MOTOR_4_MIXER_YAW == 127);

    const int16_t chip_axes[3] = { 101, -202, 303 };
    int16_t body_axes[3] = { 0, 0, 0 };
    assert(litewing_mpu6050_orient_top_0deg(chip_axes, body_axes));
    assert(body_axes[0] == -202);
    assert(body_axes[1] == 101);
    assert(body_axes[2] == -304);
    assert(!litewing_mpu6050_orient_top_0deg(NULL, body_axes));
    assert(!litewing_mpu6050_orient_top_0deg(chip_axes, NULL));

    struct litewing_output_frame frame = {{100, 200, 300, 400}};
    assert(litewing_clamp_duty(-1) == 0);
    assert(litewing_clamp_duty(1001) == 1000);
    assert(litewing_clamp_duty(321) == 321);
    assert(litewing_mpu6050_identity_valid(0x68));
    assert(!litewing_mpu6050_identity_valid(0x70));
    assert(litewing_arm_allowed(true, true, true, true));
    assert(!litewing_arm_allowed(true, true, false, true));
    assert(!litewing_arm_allowed(true, true, true, false));

    struct litewing_output_state state = {
        .hardware_ready = true,
        .imu_healthy = true,
        .link_fresh = true,
        .armed = true,
        .failsafe = false,
        .shutdown = false,
    };
    struct litewing_output_frame sanitized = {{0, 0, 0, 0}};
    assert(litewing_output_allowed(&state));
    litewing_sanitize_frame(&frame, &state, &sanitized);
    assert(sanitized.duty[0] == 100);
    assert(sanitized.duty[3] == 400);
    frame.duty[0] = 2001;
    litewing_sanitize_frame(&frame, &state, &sanitized);
    assert(sanitized.duty[0] == LITEWING_ACTUATOR_MAX);
    state.imu_healthy = false;
    litewing_sanitize_frame(&frame, &state, &sanitized);
    for (uint32_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        assert(sanitized.duty[index] == 0);
    }
    state.imu_healthy = true;
    state.hardware_ready = false;
    assert(!litewing_output_allowed(&state));
    state.hardware_ready = true;
    state.link_fresh = false;
    assert(!litewing_output_allowed(&state));
    state.link_fresh = true;
    state.armed = false;
    assert(!litewing_output_allowed(&state));
    state.armed = true;
    state.failsafe = true;
    assert(!litewing_output_allowed(&state));
    state.failsafe = false;
    state.shutdown = true;
    assert(!litewing_output_allowed(&state));
    litewing_sanitize_frame(0, &state, &sanitized);
    for (uint32_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        assert(sanitized.duty[index] == 0);
    }
    litewing_safe_frame(&frame);
    for (uint32_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        assert(frame.duty[index] == 0);
    }
    return 0;
}
