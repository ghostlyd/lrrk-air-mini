#ifndef LITEWING_IMU_HEALTH_H
#define LITEWING_IMU_HEALTH_H

#include <stdbool.h>
#include <stdint.h>

struct lw_imu_observation {
    /* Caller supplies successful compatible-sensor probe evidence, not board identity. */
    bool identity_verified;
    uint8_t who_am_i;
    bool sample_seen;
    bool healthy;
    uint32_t sample_ms;
};

struct lw_imu_timing {
    /* Local diagnostic snapshot; NOT part of the existing nine-byte v1 wire
     * export. Counters saturate and reset with observation invalidation. */
    uint32_t notification_timeouts;
    uint32_t read_failures;
    uint32_t last_wait_us;
    uint32_t last_read_us;
    uint32_t max_read_us;
};

/* Pure v1 serializer. Both pointers must be valid; output has at least 9 bytes.
 * Caller supplies a coherent observation and the driver's existing stale timeout.
 * Age is unsigned elapsed milliseconds (one uint32_t clock cycle), or UINT32_MAX
 * without a sample. Health: 0 unknown, 1 healthy, 2 unhealthy. A false driver
 * health flag is explicit unhealthy only after sample_seen; expired healthy is
 * unknown. This function neither probes hardware nor changes driver state.
 */
void lw_imu_health_export(const struct lw_imu_observation *observation,
                          uint32_t now_ms, uint32_t timeout_ms, uint8_t output[9]);

#endif
