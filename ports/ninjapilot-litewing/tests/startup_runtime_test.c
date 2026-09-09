/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Characterize the existing integration, not a proposed runtime fix.
 * Only RTOS clocks/snapshots/locking are faked. Both production C files run. */
#include <pios.h>
#include <stdio.h>
#include RUNTIME_SOURCE
#include MONITOR_SOURCE

static uint32_t now_us, idle_us;
static bool missing_idle;
static int idle_token, mutex_token;
static unsigned lock_depth;
uint32_t test_clock(void) { return now_us; }
void *pios_malloc(size_t size) { return calloc(1, size); }
xSemaphoreHandle xSemaphoreCreateRecursiveMutex(void) { return &mutex_token; }
void xSemaphoreTakeRecursive(xSemaphoreHandle mutex, uint32_t timeout) {
    assert(mutex == &mutex_token && timeout == UINT32_MAX); ++lock_depth;
}
void xSemaphoreGiveRecursive(xSemaphoreHandle mutex) {
    assert(mutex == &mutex_token && lock_depth > 0); --lock_depth;
}
UBaseType_t uxTaskGetStackHighWaterMark(TaskHandle_t task) { (void)task; return 100; }
TaskHandle_t xTaskGetIdleTaskHandle(void) { return &idle_token; }
UBaseType_t uxTaskGetSystemState(TaskStatus_t *tasks, UBaseType_t capacity, uint32_t *total) {
    assert(capacity >= 1);
    if (total) *total = now_us;
    if (missing_idle) return 0;
    tasks[0] = (TaskStatus_t){ .xHandle = &idle_token, .pcTaskName = "IDLE1",
        .eCurrentState = eReady, .ulRunTimeCounter = idle_us, .xCoreID = 1 };
    return 1;
}
int main(int argc, char **argv) {
    assert(argc == 2);
    now_us = 1000;
    assert(PIOS_TASK_MONITOR_Initialize(1) == 0);
    /* Known input: 50000 us of idle accumulated before the first observation.
     * Current shim throws this interval away to establish a baseline. */
    now_us = 101000; idle_us = 50000;
    unsigned first = PIOS_TASK_MONITOR_GetIdlePercentage();
    assert(first == 0);
    unsigned second;
    if (strcmp(argv[1], "missing-idle") == 0) {
        missing_idle = true; now_us = 201000; idle_us = 100000;
        second = PIOS_TASK_MONITOR_GetIdlePercentage();
        assert(second == 0); /* Missing snapshot is indistinguishable from busy. */
    } else if (strcmp(argv[1], "wrap") == 0) {
        /* Establish matching baselines near wrap, then cross it together. */
        now_us = UINT32_MAX - 50000; idle_us = UINT32_MAX - 10000;
        (void)PIOS_TASK_MONITOR_GetIdlePercentage();
        now_us += 100000; idle_us += 50000;
        second = PIOS_TASK_MONITOR_GetIdlePercentage();
        assert(second == 50);
    } else {
        unsigned percent = (unsigned)strtoul(argv[1], NULL, 10);
        assert(percent == 20 || percent == 50 || percent == 80);
        now_us = 201000; idle_us += percent * 1000;
        second = PIOS_TASK_MONITOR_GetIdlePercentage();
        assert(second == percent);
    }
    assert(lock_depth == 0);
    printf("first_idle=%u second_idle=%u\n", first, second);
    free(mTaskHandles);
    return 0;
}
