#pragma once
#include "pios.h"
#include <stdio.h>
#include <uavobjectmanager.h>
#include <eventdispatcher.h>
#include <alarms.h>
typedef xTaskHandle TaskHandle_t;
#define MODULE_INITCALL(a, b)
void StartModules(void);
#define MODULE_TASKCREATE_ALL StartModules()
#define HEAP_LIMIT_CRITICAL 1000
#define HEAP_LIMIT_WARNING 2000
#define CPULOAD_LIMIT_CRITICAL 95
#define CPULOAD_LIMIT_WARNING 90
unsigned xPortGetFreeHeapSize(void);
unsigned uxTaskGetStackHighWaterMark(xTaskHandle);
uint8_t PIOS_TASK_MONITOR_GetIdlePercentage(void);
void vTaskDelay(unsigned);
void PIOS_SYS_Reset(void);
xQueueHandle xQueueCreate(unsigned, unsigned);
int xQueueReceive(xQueueHandle, void *, unsigned);
