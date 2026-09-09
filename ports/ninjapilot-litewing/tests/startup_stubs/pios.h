#pragma once
/* Host clock/RTOS boundary for the real pinned task monitor and runtime shim. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define PIOS_INCLUDE_TASK_MONITOR
#define configGENERATE_RUN_TIME_STATS 1
#define portMAX_DELAY UINT32_MAX
typedef void *TaskHandle_t;
typedef TaskHandle_t xTaskHandle;
typedef void *xSemaphoreHandle;
typedef uint32_t UBaseType_t;
typedef int32_t BaseType_t;
typedef uint8_t StackType_t;
typedef enum { eRunning, eReady, eBlocked, eSuspended, eDeleted, eInvalid } eTaskState;
typedef struct {
    TaskHandle_t xHandle;
    const char *pcTaskName;
    UBaseType_t xTaskNumber;
    eTaskState eCurrentState;
    UBaseType_t uxCurrentPriority, uxBasePriority;
    uint32_t ulRunTimeCounter;
    StackType_t *pxStackBase;
    uint32_t usStackHighWaterMark;
    BaseType_t xCoreID;
} TaskStatus_t;
uint32_t test_clock(void);
#define portGET_RUN_TIME_COUNTER_VALUE() test_clock()
void *pios_malloc(size_t size);
xSemaphoreHandle xSemaphoreCreateRecursiveMutex(void);
void xSemaphoreTakeRecursive(xSemaphoreHandle mutex, uint32_t timeout);
void xSemaphoreGiveRecursive(xSemaphoreHandle mutex);
UBaseType_t uxTaskGetSystemState(TaskStatus_t *tasks, UBaseType_t capacity, uint32_t *total);
UBaseType_t uxTaskGetRunTime(TaskHandle_t task);
UBaseType_t uxTaskGetStackHighWaterMark(TaskHandle_t task);
TaskHandle_t xTaskGetIdleTaskHandle(void);
#include <pios_task_monitor.h>
