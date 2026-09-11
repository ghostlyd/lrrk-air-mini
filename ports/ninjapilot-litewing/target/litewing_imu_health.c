#include "litewing_imu_health.h"

void lw_imu_health_export(const struct lw_imu_observation *observation,
                          uint32_t now_ms, uint32_t timeout_ms, uint8_t output[9])
{
    uint32_t age = observation->sample_seen ? now_ms - observation->sample_ms : UINT32_MAX;
    uint8_t health = 0;
    if (observation->sample_seen) {
        if (!observation->healthy) {
            health = 2;
        } else if (observation->identity_verified && age < timeout_ms) {
            health = 1;
        }
    }
    output[0] = (uint8_t)age;
    output[1] = (uint8_t)(age >> 8);
    output[2] = (uint8_t)(age >> 16);
    output[3] = (uint8_t)(age >> 24);
    output[4] = 1;
    output[5] = observation->identity_verified ? 1 : 0;
    output[6] = observation->who_am_i;
    output[7] = observation->sample_seen ? 1 : 0;
    output[8] = health;
}
