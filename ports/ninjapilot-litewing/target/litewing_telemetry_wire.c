/* Bounded telemetry payloads, independent of networking and object access. */
#include "litewing_telemetry_wire.h"
#include <string.h>

static uint16_t object_size(uint32_t id)
{
    switch (id) {
    case UINT32_C(0xD7E0D964): return 28;
    case UINT32_C(0xEF69B6BC): return 8;
    case UINT32_C(0x26962352): return 30;
    case UINT32_C(0x6B7639EC): return 25;
    case UINT32_C(0xB8229FE4): return 29;
    default: return 0;
    }
}

static int valid(const struct lw_telemetry_record *r)
{
    uint16_t size = object_size(r->object_id);
    return size && size == r->data_len && r->serialized_us <= INT64_MAX &&
        (r->sample_age_us == UINT64_MAX || r->sample_age_us <= r->serialized_us);
}

static uint64_t get_be(const uint8_t *p, size_t size)
{
    uint64_t value = 0;
    for (size_t i = 0; i < size; ++i) value = (value << 8) | p[i];
    return value;
}

static void put_be(uint8_t *p, uint64_t value, size_t size)
{
    for (size_t i = 0; i < size; ++i) p[i] = (uint8_t)(value >> (8 * (size - i - 1)));
}

int lw_telemetry_payload_encode(const struct lw_telemetry_record *r,
                                uint8_t *wire, size_t capacity, size_t *written)
{
    if (!written) return -1;
    *written = 0;
    if (!r || !wire || !valid(r) || capacity < (size_t)24 + r->data_len) return -1;
    wire[0] = 1;
    wire[1] = 0;
    put_be(wire + 2, r->data_len, 2);
    put_be(wire + 4, r->object_id, 4);
    put_be(wire + 8, r->serialized_us, 8);
    put_be(wire + 16, r->sample_age_us, 8);
    memcpy(wire + 24, r->data, r->data_len);
    *written = 24 + r->data_len;
    return 0;
}

int lw_telemetry_payload_decode(const uint8_t *wire, size_t length,
                                struct lw_telemetry_record *out)
{
    if (!out) return -1;
    memset(out, 0, sizeof(*out));
    if (!wire || length < 32 || length > 54 || wire[0] != 1 || wire[1]) return -1;
    struct lw_telemetry_record r = {0};
    r.data_len = (uint16_t)get_be(wire + 2, 2);
    r.object_id = (uint32_t)get_be(wire + 4, 4);
    r.serialized_us = get_be(wire + 8, 8);
    r.sample_age_us = get_be(wire + 16, 8);
    if (!valid(&r) || length != (size_t)24 + r.data_len) return -1;
    memcpy(r.data, wire + 24, r.data_len);
    *out = r;
    return 0;
}

int lw_telemetry_frame_validate(const struct lw_wire_frame *frame,
                                struct lw_telemetry_record *out)
{
    if (!out) return -1;
    memset(out, 0, sizeof(*out));
    if (!frame || frame->direction != 1 || frame->kind != 8 || !frame->sequence) return -1;
    uint8_t session = 0, challenge = 0;
    for (size_t i = 0; i < 16; ++i) {
        session |= frame->session[i];
        challenge |= frame->challenge[i];
    }
    if (!session || challenge) return -1;
    return lw_telemetry_payload_decode(frame->payload, frame->payload_len, out);
}
