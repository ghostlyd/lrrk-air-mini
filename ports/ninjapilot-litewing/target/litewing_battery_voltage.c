#include "litewing_battery_voltage.h"
#include <math.h>

void litewing_battery_update(struct litewing_battery_sample *sample,
                             int pad_mv, bool calibrated, int64_t captured_us)
{
    *sample = (struct litewing_battery_sample){0};
    /* Bound before multiplication. Zero is not evidence of a present pack.
     * This electrical input bound is not a safe-pack-voltage threshold.
     */
    if (!calibrated || pad_mv <= 0 || pad_mv > 3300 || captured_us < 0) {
        return;
    }
    /* Candidate V2.6.C R26/R27 are equal 100K resistors. Fitted-board scale
     * still requires comparison with a meter before flight qualification.
     */
    sample->millivolts = (uint32_t)pad_mv * 2u;
    sample->captured_us = captured_us;
    sample->valid = true;
}

bool litewing_battery_read(const struct litewing_battery_sample *sample,
                           int64_t now_us, uint32_t *battery_mv)
{
    *battery_mv = 0;
    if (!sample->valid || sample->captured_us < 0 || now_us < sample->captured_us
        || now_us - sample->captured_us > 500000) {
        return false;
    }
    *battery_mv = sample->millivolts;
    return true;
}

void litewing_battery_export(const struct litewing_battery_sample *sample,
                             int64_t now_us, float fields[7])
{
    for (unsigned i = 0; i < 7; ++i) {
        fields[i] = NAN;
    }
    uint32_t millivolts;
    if (litewing_battery_read(sample, now_us, &millivolts)) {
        fields[0] = (float)millivolts / 1000.0f;
    }
}
