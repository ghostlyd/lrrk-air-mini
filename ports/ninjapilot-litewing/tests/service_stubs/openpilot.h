#pragma once
#include "board_test.h"
#include <utlist.h>
#include <eventdispatcher.h>
#define tskIDLE_PRIORITY 0
#define portTICK_RATE_MS 1
#define portMAX_DELAY UINT32_MAX
#define pdTRUE 1
typedef void *xSemaphoreHandle;
#include <pios_callbackscheduler.h>
xSemaphoreHandle xSemaphoreCreateRecursiveMutex(void);
int xSemaphoreTakeRecursive(xSemaphoreHandle, uint32_t);
int xSemaphoreGiveRecursive(xSemaphoreHandle);
void vSemaphoreDelete(xSemaphoreHandle);
xQueueHandle xQueueCreate(unsigned, unsigned);
void vQueueDelete(xQueueHandle);
int xQueueSend(xQueueHandle, const void *, unsigned);
int xQueueReceive(xQueueHandle, void *, unsigned);
uint32_t xTaskGetTickCount(void);
