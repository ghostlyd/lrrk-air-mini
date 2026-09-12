#include "litewing_attitude_trace.h"
#include <assert.h>
#include <string.h>
int main(void)
{
    static struct lw_trace t;
    struct lw_trace_record r = {0}, out = {.timestamp_us = 9999};
    assert(!lw_trace_read(&t, 0, &out) && out.timestamp_us == 9999);
    for (unsigned i = 0; i < 1000; ++i) {
        r.timestamp_us = i;
        lw_trace_push(&t, &r, false);
    }
    assert(t.count == 64 && !t.triggered);
    for (unsigned i = 1000; i < 1448; ++i) {
        r.timestamp_us = i;
        r.pre_bias[0] = (float)i;
        r.applied_bias[0] = -(float)i;
        /* Only first post sample is powered: zero does not restart capture. */
        lw_trace_push(&t, &r, i == 1000);
    }
    assert(t.frozen && t.count == 512 && t.trigger_index == 64);
    for (unsigned i = 0; i < 512; ++i) {
        assert(lw_trace_read(&t, i, &out));
        assert(out.timestamp_us == 936 + i && out.sequence == 936 + i);
        if (i >= 64) {
            assert(out.pre_bias[0] == (float)(936 + i));
            assert(out.applied_bias[0] == -(float)(936 + i));
        }
    }
    r.timestamp_us = 999999;
    lw_trace_push(&t, &r, true);
    assert(lw_trace_read(&t, 511, &out) && out.timestamp_us == 1447);
    assert(!lw_trace_read(&t, 512, &out) && out.timestamp_us == 1447);
    assert(!lw_trace_read(&t, 65535, &out));
    memset(&t, 0, sizeof t);
    for (unsigned i = 0; i < 511; ++i) lw_trace_push(&t, &r, i == 0);
    assert(!t.frozen && t.trigger_index == 0);
    assert(!lw_trace_read(&t, 0, &out));
    lw_trace_push(&t, &r, false);
    assert(t.frozen && lw_trace_read(&t, 511, &out) && out.sequence == 511);
    return 0;
}
