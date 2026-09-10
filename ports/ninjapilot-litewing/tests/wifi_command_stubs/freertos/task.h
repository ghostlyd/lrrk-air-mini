#pragma once
#include "FreeRTOS.h"
typedef void (*TaskFunction_t)(void *);
typedef void *TaskHandle_t;
BaseType_t xTaskCreate(TaskFunction_t, const char *, uint32_t, void *, UBaseType_t, TaskHandle_t *);
void vTaskDelay(TickType_t);
void vTaskDelete(TaskHandle_t);
