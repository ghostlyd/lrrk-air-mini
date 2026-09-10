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

bool litewing_battery_process_dma(struct litewing_battery_sample *sample,
                                  const uint32_t *words, size_t count,
                                  int64_t captured_us, int64_t now_us,
                                  litewing_battery_calibrate_fn calibrate,
                                  void *context)
{
    *sample = (struct litewing_battery_sample){0};
    if (!words || !calibrate || count != 16 || captured_us < 0
        || now_us < captured_us || now_us - captured_us > 500000) {
        return false;
    }
    uint32_t sum_mv = 0;
    for (size_t i = 0; i < count; ++i) {
        /* Pinned IDF 5.3.2 ESP32-S3 TYPE2: data[11:0], channel[16:13],
         * unit[17]. Reserved bits are ignored as in the SDK bitfield view.
         * Reject ADC rail codes: clipping is not a calibrated measurement.
         */
        int raw = (int)(words[i] & 0xFFFu);
        unsigned channel = (words[i] >> 13) & 0xFu;
        unsigned unit = (words[i] >> 17) & 1u;
        if (channel != 1 || unit != 0 || raw == 0 || raw == 4095) {
            return false;
        }
        int pad_mv = 0;
        if (calibrate(context, raw, &pad_mv) != 0 || pad_mv <= 0 || pad_mv > 3300) {
            return false;
        }
        sum_mv += (uint32_t)pad_mv;
    }
    /* Calibrate individually before averaging; curve fitting is nonlinear.
     * At most 16*3300 mV accumulate, safely within uint32_t.
     */
    litewing_battery_update(sample, (int)((sum_mv + 8u) / 16u), true, captured_us);
    return sample->valid;
}

bool litewing_battery_acquire(struct litewing_battery_sample *sample, bool *faulted,
                              const struct litewing_battery_acquisition_ops *ops,
                              void *context)
{
    *sample = (struct litewing_battery_sample){0};
    if (*faulted) {
        return false;
    }
    if (ops->flush(context) != 0) {
        *faulted = true;
        return false;
    }
    /* Start time is a conservative lower bound for every sample in this burst.
     * It remains valid even when the worker resumes long after DMA completes.
     */
    int64_t captured_us = ops->clock(context);
    if (ops->start(context) != 0) {
        *faulted = true;
        (void)ops->stop(context);  /* best effort, never permits a retry */
        return false;
    }
    uint32_t words[16];
    size_t count = 0;
    int read_result = ops->read(context, words, 16, &count, 20);
    if (ops->stop(context) != 0) {
        *faulted = true;
        return false;
    }
    /* Stop must quiesce callbacks before overflow inspection. No completion
     * callback is treated as acceptance of a ring-buffer frame.
     */
    if (read_result != 0 || ops->overflowed(context) != 0) {
        return false;
    }
    return litewing_battery_process_dma(sample, words, count, captured_us,
                                        ops->clock(context), ops->calibrate, context);
}
