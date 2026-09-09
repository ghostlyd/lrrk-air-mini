#include "litewing_mpu6050_protocol.h"

static int16_t decode_i16(const uint8_t *bytes)
{
    return (int16_t)(((uint16_t)bytes[0] << 8) | bytes[1]);
}

bool litewing_mpu6050_decode_frame(const uint8_t *frame, size_t length,
                                   struct litewing_mpu6050_sample *sample)
{
    if (frame == 0 || sample == 0 || length != 14u) {
        return false;
    }

    sample->accel[0] = decode_i16(&frame[0]);
    sample->accel[1] = decode_i16(&frame[2]);
    sample->accel[2] = decode_i16(&frame[4]);
    sample->temperature = decode_i16(&frame[6]);
    sample->gyro[0] = decode_i16(&frame[8]);
    sample->gyro[1] = decode_i16(&frame[10]);
    sample->gyro[2] = decode_i16(&frame[12]);
    return true;
}

bool litewing_mpu6050_sample_is_fresh(bool sample_seen, uint32_t now_ms,
                                      uint32_t sample_ms, uint32_t timeout_ms)
{
    if (!sample_seen || timeout_ms == 0u) {
        return false;
    }

    /* Unsigned subtraction deliberately handles a 32-bit millisecond wrap. */
    return (uint32_t)(now_ms - sample_ms) <= timeout_ms;
}
