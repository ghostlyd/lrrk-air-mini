#pragma once
#include "pios.h"
#include <stdio.h>
#include <math.h>
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
void vQueueDelete(xQueueHandle);
xTaskHandle xTaskGetCurrentTaskHandle(void);
void PIOS_SYS_Init(void);
void InitModules(void);
int32_t SystemModInitialize(void);
bool PIOS_LiteWing_BoardServicesInitialized(void);
#define MODULE_INITIALISE_ALL do { InitModules(); SystemModInitialize(); } while (0)
