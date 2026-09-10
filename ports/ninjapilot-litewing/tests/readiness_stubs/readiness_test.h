#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef uint32_t TickType_t;
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))

typedef enum {
    SYSTEMALARMS_ALARM_UNINITIALISED = 0,
    SYSTEMALARMS_ALARM_OK = 1,
    SYSTEMALARMS_ALARM_WARNING = 2,
    SYSTEMALARMS_ALARM_CRITICAL = 3,
    SYSTEMALARMS_ALARM_ERROR = 4,
} SystemAlarmsAlarmOptions;

typedef enum {
    SYSTEMALARMS_ALARM_BOOTFAULT = 1,
} SystemAlarmsAlarmElem;

enum {
    TASKINFO_RUNNING_SYSTEM = 0,
    TASKINFO_RUNNING_RECEIVER = 5,
    TASKINFO_RUNNING_ACTUATOR = 7,
    TASKINFO_RUNNING_ATTITUDE = 9,
    TASKINFO_RUNNING_TELEMETRYTX = 14,
    TASKINFO_RUNNING_TELEMETRYRX = 15,
};

SystemAlarmsAlarmOptions AlarmsGet(SystemAlarmsAlarmElem alarm);
int32_t AlarmsClear(SystemAlarmsAlarmElem alarm);
bool PIOS_TASK_MONITOR_IsRunning(uint16_t task_id);
bool PIOS_LiteWing_BoardServicesInitialized(void);
bool PIOS_LiteWing_MPU6050_IsHealthy(void);
TickType_t xTaskGetTickCount(void);
void vTaskDelay(TickType_t ticks);
