/* Memory-safety corpus, not a cryptographic known-answer test.
 * The stub supplies a deterministic tag; real HMAC is tested separately.
 */
#include "litewing_pilot_wire.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

static int tag_stub(void *ctx, const uint8_t *message, size_t length, uint8_t tag[32])
{
    (void)message; (void)length;
    memset(tag, 0xa5, 32);
    return ctx ? -1 : 0;
}

int main(void)
{
    struct lw_wire_frame frame = {.direction=0, .kind=5, .sequence=UINT64_MAX};
    struct lw_wire_frame decoded;
    for (unsigned payload = 0; payload <= 512; ++payload) {
        frame.payload_len = payload;
        memset(frame.payload, 0x35, payload);
        size_t length = 82 + payload;
        uint8_t *wire = malloc(length);
        assert(wire);
        size_t written = 77;
        for (size_t cap = 0; cap < length; ++cap) {
            assert(lw_wire_encode(&frame, tag_stub, NULL, wire, cap, &written) == -1);
            assert(written == 0);
        }
        assert(lw_wire_encode(&frame, tag_stub, NULL, wire, length, &written) == 0);
        assert(written == length);
        assert(lw_wire_decode(wire, length, 0, tag_stub, NULL, &decoded) == 0);
        assert(decoded.sequence == UINT64_MAX && decoded.payload_len == payload);
        assert(!memcmp(decoded.payload, frame.payload, payload));
        for (size_t cut = 0; cut < length; ++cut) {
            uint8_t *short_wire = malloc(cut ? cut : 1);
            assert(short_wire);
            memcpy(short_wire, wire, cut);
            assert(lw_wire_decode(short_wire, cut, 0, tag_stub, NULL, &decoded) == -1);
            free(short_wire);
        }
        wire[length-1] ^= 1;
        assert(lw_wire_decode(wire, length, 0, tag_stub, NULL, &decoded) == -1);
        assert(lw_wire_encode(&frame, tag_stub, &frame, wire, length, &written) == -1);
        assert(written == 0);
        for (size_t i = 0; i < length; ++i) assert(wire[i] == 0);
        free(wire);
    }
    return 0;
}
