#pragma once
#include <stddef.h>
#include <stdint.h>

/* Codec result is not permission to act: caller enforces session/age/ownership.
 * Buffers and frame arguments must not overlap. MAC context is caller-owned.
 */
struct lw_wire_frame {
    uint8_t direction, kind;
    uint8_t session[16];
    uint64_t sequence;
    uint8_t challenge[16];
    uint16_t payload_len;
    uint8_t payload[512];
};
typedef int (*lw_wire_mac_fn)(void *, const uint8_t *, size_t, uint8_t[32]);
int lw_wire_decode(const uint8_t *, size_t, uint8_t, lw_wire_mac_fn, void *, struct lw_wire_frame *);
/* On error written is zero; never transmit a buffer from a failed call. */
int lw_wire_encode(const struct lw_wire_frame *, lw_wire_mac_fn, void *, uint8_t *, size_t, size_t *);
