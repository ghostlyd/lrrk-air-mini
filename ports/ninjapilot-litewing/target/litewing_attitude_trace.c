#include "litewing_attitude_trace.h"
void lw_trace_push(struct lw_trace *t, const struct lw_trace_record *r, bool powered)
{
    if (!t || !r || t->frozen) return;
    if (!t->triggered && powered) {
        t->triggered = true;
        t->trigger_index = t->count;
    }
    unsigned slot;
    if (!t->triggered && t->count == LW_TRACE_PRETRIGGER) {
        /* Advance the window, then append at its new chronological tail. */
        t->head = (t->head + 1u) % LW_TRACE_CAPACITY;
        /* The rolling window occupies 64 of 512 slots, not a 64-slot ring. */
        slot = (t->head + t->count - 1u) % LW_TRACE_CAPACITY;
    } else {
        slot = (t->head + t->count) % LW_TRACE_CAPACITY;
        ++t->count;
    }
    t->records[slot] = *r;
    t->records[slot].sequence = t->next_sequence++;
    if (t->count == LW_TRACE_CAPACITY) t->frozen = true;
}
bool lw_trace_read(const struct lw_trace *t, uint16_t i, struct lw_trace_record *out)
{
    if (!t || !out || !t->frozen || i >= t->count) return false;
    *out = t->records[(t->head + i) % LW_TRACE_CAPACITY];
    return true;
}
