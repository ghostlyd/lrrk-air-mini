/* Voltage-only telemetry module. No arming, settings, or actuator writes. */
#include "openpilot.h"
#include "flightbatterystate.h"
#include "pios_litewing_battery.h"
#include "litewing_battery_pack.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static bool init_attempted, initialized, start_attempted;

static int publish(const struct litewing_battery_sample *sample)
{
    LiteWingBatteryStoreSample(sample);
    float values[7];
    litewing_battery_export(sample, esp_timer_get_time(), values);
    FlightBatteryStateData data = {
        .Voltage=values[0], .Current=values[1], .BoardSupplyVoltage=values[2],
        .PeakCurrent=values[3], .AvgCurrent=values[4], .ConsumedEnergy=values[5],
        .EstimatedFlightTime=values[6], .NbCells=1, .NbCellsAutodetected=0,
    };
    int result = FlightBatteryStateSet(&data);
    if (result != 0) {
        struct litewing_battery_sample unknown = {0};
        LiteWingBatteryStoreSample(&unknown);
    }
    return result;
}

static void battery_worker(void *argument)
{
    (void)argument;
    /* Interrupt allocation and every ADC operation stay on this pinned worker.
     * Failure yields unknown voltage; it does not change the arming policy.
     */
    bool available = PIOS_LiteWing_BatteryADC_Init() == 0;
    for (;;) {
        struct litewing_battery_sample sample = {0};
        if (available && !PIOS_LiteWing_BatteryADC_Read(&sample))
            sample = (struct litewing_battery_sample){0};
        if (publish(&sample) != 0) {
            /* A failed storage publication cannot count as current telemetry.
             * Latch off acquisition and keep attempting unknown publications.
             */
            available = false;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

int32_t LiteWingBatteryInitialize(void)
{
    if (init_attempted) return -1;
    init_attempted = true;
    if (!FlightBatteryStateHandle()) return -1;
    UAVObjMetadata metadata;
    if (FlightBatteryStateGetMetadata(&metadata) != 0) return -1;
    /* Publish on change; the UAVTalk pack boundary independently expires
     * samples for explicit requests and already-queued updates too.
     */
    UAVObjSetTelemetryUpdateMode(&metadata, UPDATEMODE_ONCHANGE);
    metadata.telemetryUpdatePeriod = 0;
    if (FlightBatteryStateSetMetadata(&metadata) != 0) return -1;
    struct litewing_battery_sample unknown = {0};
    if (publish(&unknown) != 0) return -1;
    initialized = true;
    return 0;
}

int32_t LiteWingBatteryStart(void)
{
    if (!initialized || start_attempted) return -1;
    start_attempted = true;
    /* Native IDF pinned-task API takes BYTES, unlike the inherited PiOS
     * xTaskCreate wrapper. Low priority; sampling never runs in a flight loop.
     */
    return xTaskCreatePinnedToCore(battery_worker, "Battery", 3072, NULL, 1,
                                   NULL, 0) == pdPASS ? 0 : -1;
}
