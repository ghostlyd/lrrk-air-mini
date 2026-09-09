#pragma once
/* Host-only OS/hardware boundary; real generated objects and modules are linked. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
typedef void *xTaskHandle;
typedef void *xQueueHandle;
typedef void *xSemaphoreHandle;
typedef uint32_t portTickType;
#if !defined(TEST_ACTUATOR_LIFECYCLE) && !defined(TEST_INPUT_LIFECYCLE)
#define PIOS_EXCLUDE_ADVANCED_FEATURES
#else
#define PIOS_INCLUDE_WDG
#define PIOS_WDG_ACTUATOR 2
#endif
#define PIOS_STATIC_ASSERT(x) assert(x)
#define PIOS_Assert assert
#define MODULE_INITCALL(a, b)
#define NELEMENTS(a) (sizeof(a) / sizeof((a)[0]))
#define tskIDLE_PRIORITY 0
#define portTICK_RATE_MS 1
#define pdTRUE 1
#define pdPASS 1
#define portMAX_DELAY UINT32_MAX
#define PIOS_SERVO_BANK_MODE_PWM 0
#define PIOS_SERVO_BANK_MODE_SINGLE_PULSE 1
enum { PIOS_RCVR_TIMEOUT = -1, PIOS_RCVR_INVALID = -2, PIOS_RCVR_NODRIVER = -3 };
int xTaskCreate(void (*)(void *), const char *, unsigned, void *, unsigned, xTaskHandle *);
int32_t PIOS_TASK_MONITOR_RegisterTask(uint16_t, xTaskHandle);
int32_t PIOS_TASK_MONITOR_UnregisterTask(uint16_t);
xTaskHandle xTaskGetCurrentTaskHandle(void);
void vTaskDelete(xTaskHandle);
void vTaskDelay(portTickType);
void vQueueDelete(xQueueHandle);
bool PIOS_WDG_RegisterFlag(uint16_t);
bool PIOS_WDG_UpdateFlag(uint16_t);
portTickType xTaskGetTickCount(void);
void vTaskDelayUntil(portTickType *, portTickType);
xQueueHandle xQueueCreate(unsigned, unsigned);
int xQueueReceive(xQueueHandle, void *, unsigned);
xSemaphoreHandle xSemaphoreCreateRecursiveMutex(void);
void xSemaphoreTakeRecursive(xSemaphoreHandle, uint32_t);
void xSemaphoreGiveRecursive(xSemaphoreHandle);
int32_t PIOS_RCVR_Read(uint32_t, uint8_t);
void PIOS_Servo_Update(void);
void PIOS_Servo_Set(uint8_t, uint16_t);
void PIOS_Servo_SetBankMode(uint8_t, int);
void PIOS_Servo_SetHz(const uint16_t *, const uint32_t *, uint8_t);
uint8_t PIOS_Servo_GetPinBank(uint8_t);
#include <uavobjectmanager.h>
#include <alarms.h>
#ifdef __clang__
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wimplicit-const-int-float-conversion"
#endif
#include <mathmisc.h>
#ifdef __clang__
#pragma clang diagnostic pop
#endif
