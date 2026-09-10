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

    /* Exercise authenticated active transitions and truncated control buffers. */
    lw_session_init(&state);
    assert(lw_session_receive(&state, wire, length, root.bytes, 100, 1, 1,
        random_bytes, &counter, reply, sizeof(reply), &written) == LW_HANDSHAKE_REPLY);
    struct lw_wire_frame control = {0};
    control.kind = 3;
    control.sequence = 1;
    memcpy(control.session, state.session, 16);
    memcpy(control.challenge, state.challenge, 16);
    struct lw_pilot_mac_key pilot;
    memcpy(pilot.bytes, state.keys.c2b, 32);
    assert(lw_wire_encode(&control, lw_pilot_mac, &pilot, wire, sizeof(wire), &length) == 0);
    assert(lw_session_receive(&state, wire, length, root.bytes, 200, 1, 1,
        random_bytes, &counter, reply, sizeof(reply), &written) == LW_HANDSHAKE_REPLY);
    control.kind = 5;
    control.sequence = 2;
    control.payload_len = 16;
    for (unsigned i = 0; i < 8; ++i) {
        control.payload[2*i] = 0x05;
        control.payload[2*i+1] = 0xdc;
    }
    assert(lw_wire_encode(&control, lw_pilot_mac, &pilot, wire, sizeof(wire), &length) == 0);
    for (size_t n = 0; n < length; ++n) {
        uint8_t *short_wire = malloc(n ? n : 1);
        assert(short_wire);
        memcpy(short_wire, wire, n);
        assert(lw_session_prepare_control(&state, short_wire, n, 300) == LW_REJECT);
        free(short_wire);
    }
    struct lw_pilot_candidate candidate;
    assert(lw_session_prepare_control(&state, wire, length, 300) == LW_PILOT_CANDIDATE);
    assert(lw_session_commit_control(&state, 400, 1, &candidate) == LW_PILOT_CANDIDATE);
    assert(candidate.origin_us == 100 && candidate.sequence == 2);
    for (unsigned i = 0; i < 8; ++i) assert(candidate.channels[i] == 1500);
    assert(lw_session_prepare_control(&state, wire, length, 500) == LW_REJECT);
    control.kind = 6;
    control.sequence = 3;
    control.payload_len = 0;
    assert(lw_wire_encode(&control, lw_pilot_mac, &pilot, wire, sizeof(wire), &length) == 0);
    assert(lw_session_prepare_control(&state, wire, length, 600) == LW_RETIRED);
    assert(lw_session_commit_control(&state, 700, 1, &candidate) == LW_REJECT);
    for (size_t i = 0; i < sizeof(candidate); ++i) assert(((uint8_t *)&candidate)[i] == 0);
    return 0;
}
