/* Observation-only telemetry. Publication cannot write motor or arming state. */
#include "openpilot.h"
#include "litewingimuhealth.h"
#include "litewingimutiming.h"
#include "pios_litewing_mpu6050.h"
#include "litewing_imu_health_pack.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static portMUX_TYPE publication_lock = portMUX_INITIALIZER_UNLOCKED;
static bool publication_available;
static bool init_attempted, initialized, start_attempted;

int32_t LiteWingImuTimingPack(UAVObjHandle obj, uint16_t instance, uint8_t *data)
{
    if (!obj || !data || instance != 0 || UAVObjGetID(obj) != LITEWINGIMUTIMING_OBJID ||
        UAVObjGetNumBytes(obj) != 21) return -1;
    struct lw_imu_timing snapshot;
    PIOS_LiteWing_MPU6050_GetTiming(&snapshot);
    uint32_t values[5] = { snapshot.notification_timeouts, snapshot.read_failures,
        snapshot.last_wait_us, snapshot.last_read_us, snapshot.max_read_us };
    for (unsigned i=0;i<5;i++)
        for (unsigned j=0;j<4;j++) data[4*i+j]=(uint8_t)(values[i]>>(8*j));
    data[20]=1;
    return 0;
}

static void publication_enable(bool available)
{
    portENTER_CRITICAL(&publication_lock);
    publication_available = available;
    portEXIT_CRITICAL(&publication_lock);
}

int32_t LiteWingImuHealthPack(UAVObjHandle obj, uint16_t instance, uint8_t *data)
{
    if (!data || instance != 0 || UAVObjGetID(obj) != LITEWINGIMUHEALTH_OBJID ||
        UAVObjGetNumBytes(obj) != 9) return -1;
    struct lw_imu_observation snapshot = {0};
    int64_t sample_us = 0;
    PIOS_LiteWing_MPU6050_GetTimedObservation(&snapshot, &sample_us);
    int64_t now = esp_timer_get_time();
    portENTER_CRITICAL(&publication_lock);
    bool available = publication_available;
    portEXIT_CRITICAL(&publication_lock);
    if (!available || now < 0 || sample_us < 0 || now < sample_us)
        snapshot = (struct lw_imu_observation){0};
    /* Normalize a 64-bit monotonic elapsed time into the pure v1 exporter's
     * single-cycle contract. Saturation cannot turn old samples healthy. */
    uint64_t age = snapshot.sample_seen ? (uint64_t)(now - sample_us) / 1000 : UINT32_MAX;
    uint32_t bounded_age = age >= UINT32_MAX ? UINT32_MAX : (uint32_t)age;
    snapshot.sample_ms = 0;
    lw_imu_health_export(&snapshot, bounded_age,
                         LITEWING_MPU6050_STALE_TIMEOUT_MS, data);
    return 0;
}

static int publish_health(void)
{
    uint8_t wire[9];
    LiteWingIMUHealthData data;
    _Static_assert(sizeof(data) == 9, "IMU health schema changed");
    if (LiteWingImuHealthPack(LiteWingIMUHealthHandle(), 0, wire) != 0) return -1;
    memcpy(&data, wire, sizeof(data));
    int result = LiteWingIMUHealthSet(&data);
    if (result != 0) publication_enable(false);
    return result;
}

static void imu_health_worker(void *argument)
{
    (void)argument;
    for (;;) {
        (void)publish_health();
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

int32_t LiteWingImuHealthInitialize(void)
{
    if (init_attempted) return -1;
    init_attempted = true;
    /* UAVObjectsInitializeAll covers upstream only. Register our generated
     * object before any publisher or Telemetry module enumerates objects. */
    if (LiteWingIMUHealthInitialize() != 0 || !LiteWingIMUHealthHandle() ||
        LiteWingIMUTimingInitialize() != 0 || !LiteWingIMUTimingHandle()) return -1;
    UAVObjMetadata timing_metadata;
    if (LiteWingIMUTimingGetMetadata(&timing_metadata) != 0 ||
        UAVObjGetGcsAccess(&timing_metadata) != ACCESS_READONLY) return -1;
    UAVObjMetadata metadata;
    if (LiteWingIMUHealthGetMetadata(&metadata) != 0 ||
        UAVObjGetGcsAccess(&metadata) != ACCESS_READONLY) return -1;
    UAVObjSetTelemetryUpdateMode(&metadata, UPDATEMODE_ONCHANGE);
    metadata.telemetryUpdatePeriod = 0;
    if (LiteWingIMUHealthSetMetadata(&metadata) != 0 || publish_health() != 0) return -1;
    initialized = true;
    return 0;
}

int32_t LiteWingImuHealthStart(void)
{
    if (!initialized || start_attempted) return -1;
    start_attempted = true;
    publication_enable(true);
    if (xTaskCreatePinnedToCore(imu_health_worker, "IMUHealth", 2048, NULL, 1,
                               NULL, 0) != pdPASS) {
        publication_enable(false);
        return -1;
    }
    return 0;
}
