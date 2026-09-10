#pragma once
#include "litewing_pilot_wire.h"

/* No I/O, keys, replay state or authorization. Caller buffers must not overlap.
 * UINT64_MAX sample age means unknown, not a measured age. Error outputs are
 * zeroed; encode errors leave the destination untouched and written zero.
 */
struct lw_telemetry_record {
    uint32_t object_id;
    uint64_t serialized_us, sample_age_us;
    uint16_t data_len;
    uint8_t data[30];
};
int lw_telemetry_payload_encode(const struct lw_telemetry_record *, uint8_t *, size_t, size_t *);
int lw_telemetry_payload_decode(const uint8_t *, size_t, struct lw_telemetry_record *);
/* Input must already be authenticated with the telemetry-derived key.
 * This validates structure only, never session ownership or freshness. */
int lw_telemetry_frame_validate(const struct lw_wire_frame *, struct lw_telemetry_record *);
