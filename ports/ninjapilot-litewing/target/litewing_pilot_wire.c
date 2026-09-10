/* Bounded LWPL framing only. No receiver, networking, or secret provisioning. */
#include "litewing_pilot_wire.h"
#include <string.h>

enum { HEADER = 50, TAG = 32, PAYLOAD_MAX = 512 };

static int valid_kind(uint8_t direction, uint8_t kind)
{
    if (direction == 0) return kind == 1 || kind == 3 || kind == 5 || kind == 6;
    if (direction == 1) return kind == 2 || kind == 4 || kind == 7;
    return 0;
}

int lw_wire_decode(const uint8_t *wire, size_t length, uint8_t direction,
                   lw_wire_mac_fn mac, void *ctx, struct lw_wire_frame *out)
{
    if (!out) return -1;
    memset(out, 0, sizeof(*out));
    if (!wire || !mac || direction > 1 || length < HEADER + TAG ||
        length > HEADER + PAYLOAD_MAX + TAG) return -1;
    if (memcmp(wire, "LWPL", 4) || wire[4] != 1 || wire[5] != direction ||
        wire[7] != 0 || !valid_kind(wire[5], wire[6])) return -1;
    const uint16_t size = ((uint16_t)wire[48] << 8) | wire[49];
    if (size > PAYLOAD_MAX || length != (size_t)HEADER + size + TAG) return -1;
    uint8_t tag[TAG] = {0};
    if (mac(ctx, wire, HEADER + size, tag) != 0) return -1;
    /* Read every byte; no data-dependent early return during comparison. */
    volatile uint8_t difference = 0;
    for (size_t i = 0; i < TAG; ++i) difference |= tag[i] ^ wire[HEADER + size + i];
    if (difference) return -1;
    out->direction = wire[5];
    out->kind = wire[6];
    memcpy(out->session, wire + 8, 16);
    for (size_t i = 24; i < 32; ++i) out->sequence = (out->sequence << 8) | wire[i];
    memcpy(out->challenge, wire + 32, 16);
    out->payload_len = size;
    memcpy(out->payload, wire + HEADER, size);
    return 0;
}

int lw_wire_encode(const struct lw_wire_frame *frame, lw_wire_mac_fn mac, void *ctx,
                   uint8_t *wire, size_t capacity, size_t *written)
{
    if (!written) return -1;
    *written = 0;
    if (!frame || !mac || !wire || frame->payload_len > PAYLOAD_MAX ||
        !valid_kind(frame->direction, frame->kind)) return -1;
    const size_t unsigned_size = HEADER + frame->payload_len;
    if (capacity < unsigned_size + TAG) return -1;
    memcpy(wire, "LWPL", 4);
    wire[4] = 1; wire[5] = frame->direction; wire[6] = frame->kind; wire[7] = 0;
    memcpy(wire + 8, frame->session, 16);
    for (size_t i = 0; i < 8; ++i) wire[24+i] = (uint8_t)(frame->sequence >> (56-8*i));
    memcpy(wire + 32, frame->challenge, 16);
    wire[48] = (uint8_t)(frame->payload_len >> 8);
    wire[49] = (uint8_t)frame->payload_len;
    memcpy(wire + HEADER, frame->payload, frame->payload_len);
    uint8_t tag[TAG] = {0};
    if (mac(ctx, wire, unsigned_size, tag) != 0) {
        memset(wire, 0, unsigned_size + TAG);
        return -1;
    }
    memcpy(wire + unsigned_size, tag, TAG);
    *written = unsigned_size + TAG;
    return 0;
}
