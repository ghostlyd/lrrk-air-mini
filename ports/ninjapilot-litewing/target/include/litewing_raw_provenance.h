#ifndef LITEWING_RAW_PROVENANCE_H
#define LITEWING_RAW_PROVENANCE_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define LW_RAW_CAPACITY 3u
#define LW_RAW_TRUNCATED 1u
#define LW_RAW_COUNT_SATURATED 2u
#define LW_RAW_SEQUENCE_GAP 4u

/* In-memory only: serialize fields explicitly, never structure padding. */
struct lw_raw_sample {
    uint32_t sequence, start_us, end_us;
    uint8_t bytes[14];
};
struct lw_raw_batch {
    struct lw_raw_sample samples[LW_RAW_CAPACITY];
    uint32_t first_sequence, last_sequence;
    uint16_t consumed;
    uint8_t retained, flags;
};

/* Both queue endpoints allocate payload_size + sizeof(lw_raw_sample).
 * memcpy permits a legacy payload prefix that is not uint32-aligned. */
static inline void lw_raw_queue_store(void *item, size_t payload_size,
                                      const struct lw_raw_sample *sample)
{
    memcpy((uint8_t *)item + payload_size, sample, sizeof *sample);
}
static inline void lw_raw_queue_load(const void *item, size_t payload_size,
                                     struct lw_raw_sample *sample)
{
    memcpy(sample, (const uint8_t *)item + payload_size, sizeof *sample);
}

/* Caller owns and zeroes the batch at each sensor-update entry. This does not
 * restrict the flight queue drain or change any sample used by flight code. */
static inline void lw_raw_append(struct lw_raw_batch *batch,
                                 const struct lw_raw_sample *sample)
{
    if (batch->consumed == 0) {
        batch->first_sequence = sample->sequence;
    } else if (sample->sequence != (uint32_t)(batch->last_sequence + 1u)) {
        batch->flags |= LW_RAW_SEQUENCE_GAP;
    }
    batch->last_sequence = sample->sequence;
    if (batch->consumed == UINT16_MAX) {
        batch->flags |= LW_RAW_COUNT_SATURATED;
    } else {
        ++batch->consumed;
    }
    if (batch->retained < LW_RAW_CAPACITY) {
        batch->samples[batch->retained++] = *sample;
    } else {
        batch->flags |= LW_RAW_TRUNCATED;
    }
}
#endif
