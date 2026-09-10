#ifndef BATTERY_WORKER_TEST_SDK_H
#define BATTERY_WORKER_TEST_SDK_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef void *UAVObjHandle;
typedef struct { int mode; unsigned telemetryUpdatePeriod; } UAVObjMetadata;
enum { UPDATEMODE_ONCHANGE=2, pdPASS=1 };
typedef struct {
    float Voltage, Current, BoardSupplyVoltage, PeakCurrent, AvgCurrent;
    float ConsumedEnergy, EstimatedFlightTime;
    uint8_t NbCells, NbCellsAutodetected;
} FlightBatteryStateData;
#define pdMS_TO_TICKS(ms) (ms)
UAVObjHandle FlightBatteryStateHandle(void);
int FlightBatteryStateGetMetadata(UAVObjMetadata *);
int FlightBatteryStateSetMetadata(const UAVObjMetadata *);
void UAVObjSetTelemetryUpdateMode(UAVObjMetadata *, int);
int FlightBatteryStateSet(const FlightBatteryStateData *);
int xTaskCreatePinnedToCore(void (*)(void *), const char *, unsigned, void *,
                          unsigned, void *, int);
void vTaskDelay(unsigned);
int64_t esp_timer_get_time(void);
int32_t LiteWingBatteryInitialize(void);
int32_t LiteWingBatteryStart(void);
#endif
