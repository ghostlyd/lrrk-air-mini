/* Calibrated ADC pad voltage to nominal battery voltage; no hardware I/O. */
#ifndef LITEWING_BATTERY_VOLTAGE_H
#define LITEWING_BATTERY_VOLTAGE_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

struct litewing_battery_sample {
    uint32_t millivolts;
    int64_t captured_us;
    bool valid;
};

/* Zero-initialize before use. One owner must serialize update/read calls.
 * The producer supplies calibrated millivolts, NOT raw ADC counts. Call with
 * calibrated=false on acquisition/calibration/overflow errors to invalidate.
 */
void litewing_battery_update(struct litewing_battery_sample *sample,
                             int pad_mv, bool calibrated, int64_t captured_us);
/* Valid through 500 ms inclusive. Failure always clears the output value. */
bool litewing_battery_read(const struct litewing_battery_sample *sample,
                           int64_t now_us, uint32_t *battery_mv);
/* FlightBatteryState float field order from the pinned XML: Voltage, Current,
 * BoardSupplyVoltage, PeakCurrent, AvgCurrent, ConsumedEnergy, EstimatedFlightTime.
 * NaN denotes unavailable, including stale voltage. Cells must be set separately
 * to configured 1S, not autodetected. This does not serialize a UAVTalk packet.
 */
void litewing_battery_export(const struct litewing_battery_sample *sample,
                             int64_t now_us, float fields[7]);
/* Calibration callback returns zero and writes pad millivolts on success. */
typedef int (*litewing_battery_calibrate_fn)(void *context, int raw, int *pad_mv);
/* Process exactly one 64-byte ESP32-S3 TYPE2 frame (16 native uint32 words).
 * Caller owns framing and supplies a conservative timestamp for the OLDEST
 * sample, established at acquisition, not dequeue time. Caller must reject
 * overflow or lost timestamp association before calling. All calls serialized.
 */
bool litewing_battery_process_dma(struct litewing_battery_sample *sample,
                                  const uint32_t *words, size_t count,
                                  int64_t captured_us, int64_t now_us,
                                  litewing_battery_calibrate_fn calibrate,
                                  void *context);

/* Operations for an initialized, stopped ADC owned by one worker. Zero return
 * means success, except overflowed (zero means no overflow). flush must empty
 * stale data and reset overflow state while stopped; read uses word counts.
 * Clock is monotonic microseconds. No operation may publish telemetry itself.
 */
struct litewing_battery_acquisition_ops {
    int (*flush)(void *context);
    int (*start)(void *context);
    int (*read)(void *context, uint32_t *words, size_t capacity,
                size_t *count, uint32_t timeout_ms);
    int (*stop)(void *context);
    int (*overflowed)(void *context);
    int64_t (*clock)(void *context);
    litewing_battery_calibrate_fn calibrate;
};
/* One bounded burst. Lifecycle failure permanently sets faulted: the owner
 * must not retry or release ambiguously running ADC resources. A read failure
 * with successful stop may be retried in a new, flushed burst. All pointers
 * and callbacks are required and must outlive the call.
 */
bool litewing_battery_acquire(struct litewing_battery_sample *sample, bool *faulted,
                              const struct litewing_battery_acquisition_ops *ops,
                              void *context);
#endif
