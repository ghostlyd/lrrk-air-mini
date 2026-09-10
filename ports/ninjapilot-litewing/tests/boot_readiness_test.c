#include "readiness_test.h"
#include "pios_litewing_readiness.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "scenario=%s line=%d: %s\n", scenario, __LINE__, #condition); \
    exit(1); \
} } while (0)

static const char *scenario;
static TickType_t tick;
static bool board_ready = true;
static bool imu_ready = true;
static bool tasks[16];
static SystemAlarmsAlarmOptions alarm_state = SYSTEMALARMS_ALARM_UNINITIALISED;
static unsigned alarm_gets, clears, delays;

SystemAlarmsAlarmOptions AlarmsGet(SystemAlarmsAlarmElem alarm)
{
    CHECK(alarm == SYSTEMALARMS_ALARM_BOOTFAULT);
    alarm_gets++;
    return alarm_state;
}

int32_t AlarmsClear(SystemAlarmsAlarmElem alarm)
{
    CHECK(alarm == SYSTEMALARMS_ALARM_BOOTFAULT);
    clears++;
    if (!strcmp(scenario, "clear-fails")) return -1;
    if (strcmp(scenario, "clear-no-effect")) alarm_state = SYSTEMALARMS_ALARM_OK;
    return 0;
}

bool PIOS_TASK_MONITOR_IsRunning(uint16_t task_id)
{
    CHECK(task_id < sizeof(tasks) / sizeof(tasks[0]));
    return tasks[task_id];
}

bool PIOS_LiteWing_BoardServicesInitialized(void) { return board_ready; }
bool PIOS_LiteWing_MPU6050_IsHealthy(void) { return imu_ready; }
TickType_t xTaskGetTickCount(void) { return tick; }

void vTaskDelay(TickType_t ticks)
{
    CHECK(ticks == 10);
    delays++;
    tick += ticks;
    if (!strcmp(scenario, "eventual")) {
        imu_ready = true;
        tasks[TASKINFO_RUNNING_ATTITUDE] = true;
    }
    if (!strcmp(scenario, "fault-during-wait")) alarm_state = SYSTEMALARMS_ALARM_CRITICAL;
}

static void initialize(void)
{
    const unsigned required[] = {
        TASKINFO_RUNNING_SYSTEM, TASKINFO_RUNNING_RECEIVER,
        TASKINFO_RUNNING_ACTUATOR, TASKINFO_RUNNING_ATTITUDE,
        TASKINFO_RUNNING_TELEMETRYTX, TASKINFO_RUNNING_TELEMETRYRX,
    };
    for (unsigned i = 0; i < sizeof(required) / sizeof(required[0]); ++i) {
        tasks[required[i]] = true;
    }
}

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    scenario = argv[1];
    initialize();
    int expected = 0;
    if (!strcmp(scenario, "already-ok")) alarm_state = SYSTEMALARMS_ALARM_OK;
    else if (!strcmp(scenario, "board")) { board_ready = false; expected = -1; }
    else if (!strcmp(scenario, "imu")) { imu_ready = false; expected = -1; }
    else if (!strcmp(scenario, "eventual")) {
        imu_ready = false;
        tasks[TASKINFO_RUNNING_ATTITUDE] = false;
    } else if (!strcmp(scenario, "fault-during-wait")) {
        tasks[TASKINFO_RUNNING_RECEIVER] = false;
        expected = -1;
    } else if (!strcmp(scenario, "warning")) {
        alarm_state = SYSTEMALARMS_ALARM_WARNING; expected = -1;
    } else if (!strcmp(scenario, "critical")) {
        alarm_state = SYSTEMALARMS_ALARM_CRITICAL; expected = -1;
    } else if (!strcmp(scenario, "error")) {
        alarm_state = SYSTEMALARMS_ALARM_ERROR; expected = -1;
    } else if (!strcmp(scenario, "clear-fails") || !strcmp(scenario, "clear-no-effect")) {
        expected = -1;
    } else if (!strncmp(scenario, "task-", 5)) {
        unsigned id = (unsigned)strtoul(scenario + 5, NULL, 10);
        CHECK(id < sizeof(tasks) / sizeof(tasks[0]));
        tasks[id] = false;
        expected = -1;
    } else CHECK(!strcmp(scenario, "nominal"));

    CHECK(PIOS_LiteWing_ConfirmBootReady() == expected);
    if (!strcmp(scenario, "nominal")) {
        CHECK(clears == 1 && alarm_state == SYSTEMALARMS_ALARM_OK && delays == 0);
    } else if (!strcmp(scenario, "already-ok")) {
        CHECK(clears == 0 && delays == 0);
    } else if (!strcmp(scenario, "eventual")) {
        CHECK(clears == 1 && delays == 1 && tick == 10);
    } else if (!strcmp(scenario, "imu") || !strncmp(scenario, "task-", 5)) {
        CHECK(clears == 0 && delays == 100 && tick == 1000);
    } else if (!strcmp(scenario, "fault-during-wait")) {
        CHECK(clears == 0 && delays == 1 && alarm_gets == 2);
    } else if (!strcmp(scenario, "clear-no-effect")) {
        CHECK(clears == 1 && alarm_gets == 2);
    } else {
        CHECK(clears == (!strcmp(scenario, "clear-fails") ? 1u : 0u));
        CHECK(delays == 0);
    }
    return 0;
}
