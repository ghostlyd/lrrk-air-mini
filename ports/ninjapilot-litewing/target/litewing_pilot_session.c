#include "litewing_pilot_session.h"
#include "litewing_pilot_wire.h"
#include "pios_litewing_pilot_mac.h"
#include "mbedtls/platform_util.h"
#include <string.h>

void lw_session_retire(struct lw_pilot_session *s)
{
    if (!s) return;
    mbedtls_platform_zeroize(s, sizeof(*s));
    s->last_us = -1;
}

void lw_session_init(struct lw_pilot_session *s) { lw_session_retire(s); }

int lw_session_tick(struct lw_pilot_session *s, int64_t now)
{
    if (!s) return -1;
    if (now < 0 || now < s->last_us ||
        (s->phase == LW_PENDING && now - s->started_us >= 1000000) ||
        (s->phase == LW_ACTIVE && now - s->challenge_us >= 100000)) {
        lw_session_retire(s);
        return -1;
    }
    s->last_us = now;
    return 0;
}

static int read_frame(const uint8_t *wire, size_t size, const uint8_t key[32],
                      struct lw_wire_frame *frame)
{
    struct lw_pilot_mac_key mac;
    memcpy(mac.bytes, key, sizeof(mac.bytes));
    int rc = lw_wire_decode(wire, size, 0, lw_pilot_mac, &mac, frame);
    mbedtls_platform_zeroize(&mac, sizeof(mac));
    return rc;
}

static int write_frame(const struct lw_wire_frame *frame, const uint8_t key[32],
                       uint8_t *reply, size_t capacity, size_t *written)
{
    struct lw_pilot_mac_key mac;
    memcpy(mac.bytes, key, sizeof(mac.bytes));
    int rc = lw_wire_encode(frame, lw_pilot_mac, &mac, reply, capacity, written);
    mbedtls_platform_zeroize(&mac, sizeof(mac));
    return rc;
}

enum lw_session_result lw_session_receive(struct lw_pilot_session *s,
    const uint8_t *wire, size_t size, const uint8_t root[32], int64_t now,
    int disarmed, int owner_free, lw_session_rng random, void *random_ctx,
    uint8_t *reply, size_t capacity, size_t *written)
{
    struct lw_wire_frame frame = {0}, response = {0};
    struct lw_pilot_session pending;
    uint8_t board_nonce[32] = {0};
    const uint8_t zero[16] = {0};
    enum lw_session_result result = LW_REJECT;
    lw_session_init(&pending);
    if (written) *written = 0;
    if (!s || !written) goto done;
    if (lw_session_tick(s, now) != 0) { result = LW_RETIRED; goto done; }
    if (!wire || !root || !reply || disarmed != 1 || owner_free != 1) goto done;
    if (s->phase == LW_CLOSED) {
        if (read_frame(wire, size, root, &frame) != 0 || frame.kind != 1 ||
            frame.sequence != 0 || frame.payload_len != 32 ||
            memcmp(frame.session, zero, 16) || memcmp(frame.challenge, zero, 16)) goto done;
        if (!random || random(random_ctx, board_nonce, 32) != 0 ||
            random(random_ctx, pending.session, 16) != 0 ||
            random(random_ctx, pending.challenge, 16) != 0) goto failed;
        if (lw_pilot_derive_keys(root, frame.payload, board_nonce,
                                 pending.session, &pending.keys) != 0) goto failed;
        response.direction = 1;
        response.kind = 2;
        memcpy(response.session, pending.session, 16);
        memcpy(response.challenge, pending.challenge, 16);
        memcpy(response.payload, frame.payload, 32);
        memcpy(response.payload + 32, board_nonce, 32);
        response.payload_len = 64;
        if (write_frame(&response, root, reply, capacity, written) != 0) goto failed;
        pending.phase = LW_PENDING;
        pending.last_us = pending.started_us = pending.challenge_us = now;
        *s = pending;
        result = LW_HANDSHAKE_REPLY;
    } else if (s->phase == LW_PENDING) {
        if (read_frame(wire, size, s->keys.c2b, &frame) != 0 || frame.kind != 3 ||
            frame.sequence != 1 || frame.payload_len != 0 ||
            memcmp(frame.session, s->session, 16) ||
            memcmp(frame.challenge, s->challenge, 16) || now - s->challenge_us > 75000) goto done;
        response.direction = 1;
        response.kind = 4;
        response.sequence = 1;
        memcpy(response.session, s->session, 16);
        memcpy(response.challenge, s->challenge, 16);
        if (write_frame(&response, s->keys.b2c, reply, capacity, written) != 0) goto failed;
        s->phase = LW_ACTIVE;
        result = LW_HANDSHAKE_REPLY;
    }
    goto done;
failed:
    lw_session_retire(s);
    *written = 0;
    result = LW_RETIRED;
done:
    mbedtls_platform_zeroize(&pending, sizeof(pending));
    mbedtls_platform_zeroize(board_nonce, sizeof(board_nonce));
    mbedtls_platform_zeroize(&frame, sizeof(frame));
    mbedtls_platform_zeroize(&response, sizeof(response));
    return result;
}
