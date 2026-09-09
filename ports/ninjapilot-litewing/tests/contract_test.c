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
    litewing_safe_frame(&frame);
    for (uint32_t index = 0; index < LITEWING_OUTPUT_CHANNELS; ++index) {
        assert(frame.duty[index] == 0);
    }
    return 0;
}
