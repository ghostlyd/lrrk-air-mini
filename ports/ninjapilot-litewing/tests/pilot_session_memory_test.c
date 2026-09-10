#include "litewing_pilot_session.h"
#include "litewing_pilot_wire.h"
#include "pios_litewing_pilot_mac.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

static int random_bytes(void *ctx, uint8_t *out, size_t size)
{
    unsigned *counter = ctx;
    memset(out, ++*counter, size);
    return 0;
}

int main(void)
{
    struct lw_pilot_mac_key root;
    memset(&root, 'r', sizeof(root));
    struct lw_wire_frame hello = {0};
    hello.kind = 1;
    hello.payload_len = 32;
    memset(hello.payload, 'h', 32);
    uint8_t wire[594], reply[594];
    size_t length = 0, written;
    assert(lw_wire_encode(&hello, lw_pilot_mac, &root, wire, sizeof(wire), &length) == 0);
    for (size_t n = 0; n < length; ++n) {
        uint8_t *short_wire = malloc(n ? n : 1);
        assert(short_wire);
        memcpy(short_wire, wire, n);
        struct lw_pilot_session state;
        lw_session_init(&state);
        unsigned counter = 0;
        assert(lw_session_receive(&state, short_wire, n, root.bytes, 100, 1, 1,
            random_bytes, &counter, reply, sizeof(reply), &written) == LW_REJECT);
        assert(written == 0);
        free(short_wire);
    }
    for (size_t capacity = 0; capacity <= sizeof(reply); ++capacity) {
        uint8_t *exact = malloc(capacity ? capacity : 1);
        assert(exact);
        struct lw_pilot_session state;
        lw_session_init(&state);
        unsigned counter = 0;
        int rc = lw_session_receive(&state, wire, length, root.bytes, 100, 1, 1,
            random_bytes, &counter, exact, capacity, &written);
        assert(rc == (capacity < 146 ? LW_RETIRED : LW_HANDSHAKE_REPLY));
        lw_session_retire(&state);
        free(exact);
    }
    struct lw_pilot_session state;
    lw_session_init(&state);
    unsigned counter = 0;
    assert(lw_session_receive(&state, wire, length, root.bytes, 100, 1, 1,
        random_bytes, &counter, reply, sizeof(reply), &written) == LW_HANDSHAKE_REPLY);
    for (int64_t now = 20100; now <= 980100; now += 20000)
        assert(lw_session_issue_challenge(&state, root.bytes, now,
            random_bytes, &counter, reply, sizeof(reply), &written) == LW_HANDSHAKE_REPLY);
    assert(lw_session_tick(&state, 1000100) == -1);
    assert(state.phase == LW_CLOSED);
    return 0;
}
