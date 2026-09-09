#ifndef LRRK_LITEWING_MPU6050_PROTOCOL_H
#define LRRK_LITEWING_MPU6050_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* A register-burst sample in the MPU6050's wire order. */
struct litewing_mpu6050_sample {
    int16_t accel[3];
    int16_t temperature;
    int16_t gyro[3];
};

bool litewing_mpu6050_decode_frame(const uint8_t *frame, size_t length,
                                   struct litewing_mpu6050_sample *sample);
bool litewing_mpu6050_sample_is_fresh(bool sample_seen, uint32_t now_ms,
                                      uint32_t sample_ms, uint32_t timeout_ms);

#endif /* LRRK_LITEWING_MPU6050_PROTOCOL_H */
