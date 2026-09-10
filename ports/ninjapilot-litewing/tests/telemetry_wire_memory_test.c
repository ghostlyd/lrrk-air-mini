#include "litewing_telemetry_wire.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
    struct lw_telemetry_record r = {.object_id = UINT32_C(0x26962352),
        .serialized_us = INT64_MAX, .sample_age_us = UINT64_MAX, .data_len = 30};
    uint8_t wire[54];
    size_t written = 999;
    assert(lw_telemetry_payload_encode(&r, wire, sizeof(wire), &written) == 0);
    assert(written == 54);
    for (size_t n = 0; n <= 55; ++n) {
        /* Exact heap extents make any out-of-bounds access visible to ASan. */
        uint8_t *p = malloc(n ? n : 1);
        assert(p);
        memset(p, 0xa5, n ? n : 1);
        written = 999;
        int rc = lw_telemetry_payload_encode(&r, p, n, &written);
        assert(rc == (n < 54 ? -1 : 0));
        assert(written == (n < 54 ? 0 : 54));
        if (n < 54) for (size_t i = 0; i < n; ++i) assert(p[i] == 0xa5);
        memcpy(p, wire, n < 54 ? n : 54);
        struct lw_telemetry_record out;
        memset(&out, 0xa5, sizeof(out));
        rc = lw_telemetry_payload_decode(p, n, &out);
        assert(rc == (n == 54 ? 0 : -1));
        if (rc) {
            const uint8_t *bytes = (const uint8_t *)&out;
            for (size_t i = 0; i < sizeof(out); ++i) assert(bytes[i] == 0);
        }
        free(p);
    }
    struct lw_wire_frame frame = {.direction = 1, .kind = 8, .sequence = 1};
    frame.session[0] = 1;
    memcpy(frame.payload, wire, 54);
    struct lw_telemetry_record out;
    for (size_t n = 0; n <= UINT16_MAX; ++n) {
        frame.payload_len = (uint16_t)n;
        assert(lw_telemetry_frame_validate(&frame, &out) == (n == 54 ? 0 : -1));
    }
    assert(lw_telemetry_payload_decode(NULL, 54, &out) == -1);
    assert(lw_telemetry_payload_decode(wire, 54, NULL) == -1);
    assert(lw_telemetry_payload_encode(NULL, wire, 54, &written) == -1);
    assert(lw_telemetry_payload_encode(&r, NULL, 54, &written) == -1);
    assert(lw_telemetry_payload_encode(&r, wire, 54, NULL) == -1);
    assert(lw_telemetry_frame_validate(NULL, &out) == -1);
    assert(lw_telemetry_frame_validate(&frame, NULL) == -1);
    return 0;
}
