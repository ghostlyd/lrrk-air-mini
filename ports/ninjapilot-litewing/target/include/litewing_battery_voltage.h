/* Calibrated ADC pad voltage to nominal battery voltage; no hardware I/O. */
#ifndef LITEWING_BATTERY_VOLTAGE_H
#define LITEWING_BATTERY_VOLTAGE_H
#include <stdbool.h>
#include <stdint.h>

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
#endif
