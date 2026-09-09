#include <assert.h>
#include <stdint.h>

#include "litewing_mpu6050_protocol.h"

int main(void)
{
    const uint8_t frame[14] = {
        0x01, 0x02, 0xfe, 0xdc, 0x80, 0x00,
        0x00, 0x68, 0x7f, 0xff, 0x80, 0x01, 0x00, 0x10,
    };
    struct litewing_mpu6050_sample sample;

    assert(!litewing_mpu6050_decode_frame(frame, 13u, &sample));
    assert(!litewing_mpu6050_decode_frame(frame, sizeof(frame), 0));
    assert(litewing_mpu6050_decode_frame(frame, sizeof(frame), &sample));
    assert(sample.accel[0] == 0x0102);
    assert(sample.accel[1] == (int16_t)0xfedc);
    assert(sample.accel[2] == (int16_t)0x8000);
    assert(sample.temperature == 0x0068);
    assert(sample.gyro[0] == 0x7fff);
    assert(sample.gyro[1] == (int16_t)0x8001);
    assert(sample.gyro[2] == 0x0010);

    assert(!litewing_mpu6050_sample_is_fresh(false, 10u, 10u, 20u));
    assert(litewing_mpu6050_sample_is_fresh(true, 20u, 10u, 10u));
    assert(!litewing_mpu6050_sample_is_fresh(true, 31u, 10u, 20u));
    assert(litewing_mpu6050_sample_is_fresh(true, 2u, UINT32_MAX - 2u, 5u));
    assert(!litewing_mpu6050_sample_is_fresh(true, 10u, 10u, 0u));
    return 0;
}
