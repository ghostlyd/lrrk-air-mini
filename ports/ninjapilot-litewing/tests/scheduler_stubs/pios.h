#pragma once
/* RTOS boundary only; compile the complete real scheduler. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define PIOS_INCLUDE_CALLBACKSCHEDULER
/* Disable unsafe host-stack watermark writes, not scheduler algorithms. */
#define USE_SIM_POSIX
#define PIOS_Assert assert
#define PIOS_STATIC_ASSERT(c) assert(c)
#define tskIDLE_PRIORITY 0
#define portTICK_RATE_MS 1
#define portMAX_DELAY UINT32_MAX
#define pdTRUE 1
#define pdPASS 1
typedef void *xTaskHandle;
typedef void *xQueueHandle;
typedef void *xSemaphoreHandle;
typedef int BaseType_t;
typedef unsigned UBaseType_t;
typedef void (*TaskFunction_t)(void *);
void *pios_malloc(size_t);
void pios_free(void *);
xSemaphoreHandle xSemaphoreCreateRecursiveMutex(void);
xSemaphoreHandle test_binary_semaphore(void);
#define vSemaphoreCreateBinary(handle) ((handle) = test_binary_semaphore())
int xSemaphoreTakeRecursive(xSemaphoreHandle, uint32_t);
int xSemaphoreGiveRecursive(xSemaphoreHandle);
int xSemaphoreTake(xSemaphoreHandle, uint32_t);
int xSemaphoreGive(xSemaphoreHandle);
int xSemaphoreGiveFromISR(xSemaphoreHandle, long *);
void vSemaphoreDelete(xSemaphoreHandle);
uint32_t xTaskGetTickCount(void);
BaseType_t xTaskCreate(TaskFunction_t, const char *, uint32_t, void *, unsigned, xTaskHandle *);
void vTaskDelete(xTaskHandle);
int32_t PIOS_TASK_MONITOR_RegisterTask(uint16_t, xTaskHandle);
int32_t PIOS_TASK_MONITOR_UnregisterTask(uint16_t);
#include <pios_callbackscheduler.h>
