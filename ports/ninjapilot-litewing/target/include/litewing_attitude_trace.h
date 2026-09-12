#ifndef LRRK_ATTITUDE_TRACE_H
#define LRRK_ATTITUDE_TRACE_H
#include <stdbool.h>
#include <stdint.h>
#define LW_TRACE_CAPACITY 512u
#define LW_TRACE_PRETRIGGER 64u
struct lw_trace_record {
    uint64_t timestamp_us;
    uint32_t sequence;
    float dt, accel[3], gyro[3], corrected[3], rpy[3];
    float pre_bias[3], applied_bias[3];
    uint32_t commits;
    uint16_t requested[4], submitted[4];
    uint8_t pwm_available, known_mask, suppression;
};
/* Zero initialization starts capture. Caller serializes all access. */
struct lw_trace {
    struct lw_trace_record records[LW_TRACE_CAPACITY];
    uint32_t next_sequence;
    uint16_t head, count, trigger_index;
    bool triggered, frozen;
};
void lw_trace_push(struct lw_trace *, const struct lw_trace_record *, bool powered);
bool lw_trace_read(const struct lw_trace *, uint16_t, struct lw_trace_record *);
#endif
