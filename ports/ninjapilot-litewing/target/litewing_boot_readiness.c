/* Fail-closed whole-boot readiness publication for the LiteWing target. */
#include "pios_litewing_readiness.h"

#include <stdbool.h>
#include <stddef.h>

#include <alarms.h>
#include <pios_task_monitor.h>
#include <systemalarms.h>
#include <taskinfo.h>

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "pios_board.h"
#include "pios_litewing_mpu6050.h"

#define LITEWING_BOOT_READY_TIMEOUT_MS 1000u
#define LITEWING_BOOT_READY_POLL_MS 10u

static bool required_tasks_running(void)
{
    static const uint16_t required[] = {
        TASKINFO_RUNNING_SYSTEM,
        TASKINFO_RUNNING_RECEIVER,
        TASKINFO_RUNNING_ACTUATOR,
        TASKINFO_RUNNING_ATTITUDE,
        TASKINFO_RUNNING_TELEMETRYTX,
        TASKINFO_RUNNING_TELEMETRYRX,
    };
    for (size_t i = 0; i < sizeof(required) / sizeof(required[0]); ++i) {
        if (!PIOS_TASK_MONITOR_IsRunning(required[i])) {
            return false;
        }
    }
    return true;
}

int32_t PIOS_LiteWing_ConfirmBootReady(void)
{
    const TickType_t start = xTaskGetTickCount();
    const TickType_t timeout = pdMS_TO_TICKS(LITEWING_BOOT_READY_TIMEOUT_MS);
    const TickType_t poll = pdMS_TO_TICKS(LITEWING_BOOT_READY_POLL_MS);

    if (!PIOS_LiteWing_BoardServicesInitialized() || timeout == 0 || poll == 0) {
        return -1;
    }
    for (;;) {
        const SystemAlarmsAlarmOptions boot_fault =
            AlarmsGet(SYSTEMALARMS_ALARM_BOOTFAULT);
        if (boot_fault != SYSTEMALARMS_ALARM_UNINITIALISED &&
            boot_fault != SYSTEMALARMS_ALARM_OK) {
            return -1;
        }
        if (PIOS_LiteWing_MPU6050_IsHealthy() && required_tasks_running()) {
            if (boot_fault == SYSTEMALARMS_ALARM_UNINITIALISED) {
                if (AlarmsClear(SYSTEMALARMS_ALARM_BOOTFAULT) != 0 ||
                    AlarmsGet(SYSTEMALARMS_ALARM_BOOTFAULT) != SYSTEMALARMS_ALARM_OK) {
                    return -1;
                }
            }
            return 0;
        }
        if ((TickType_t)(xTaskGetTickCount() - start) >= timeout) {
            return -1;
        }
        vTaskDelay(poll);
    }
}
