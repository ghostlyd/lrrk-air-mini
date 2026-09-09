#include <assert.h>
#include <stdint.h>

#include "litewing_contract.h"

int main(void)
{
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
