#pragma once
/* Host RTOS boundary; selected feature branches and sensor ABI stay real. */
#include "../thrust_stubs/openpilot.h"
/* Consume real stack/watchdog constants, not the upstream fallback sizes. */
#include "../../target/firmware/pios_board.h"
typedef int BaseType_t;
typedef xQueueHandle QueueHandle_t;
#define USE_ESP32 1
#define PIOS_INCLUDE_ICM20602
#define PIOS_SENSOR_RATE 500.0f
#define PIOS_QUATERNION_STABILIZATION
#define portTICK_PERIOD_MS 1
#define errQUEUE_EMPTY 0
#define M_PI_F ((float)M_PI)
void *pios_malloc(size_t);
void pios_free(void *);
void vTaskDelay(portTickType);
int32_t PIOS_TASK_MONITOR_UnregisterTask(uint16_t);
uint32_t PIOS_DELAY_GetRaw(void);
uint32_t PIOS_DELAY_DiffuS(uint32_t);
#include <pios_deltatime.h>
