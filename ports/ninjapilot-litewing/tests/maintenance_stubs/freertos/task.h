#pragma once
#include "FreeRTOS.h"
#include "../../wifi_command_stubs/freertos/task.h"
uint32_t ulTaskNotifyTake(BaseType_t clear, TickType_t wait);
void xTaskNotifyGive(TaskHandle_t task);
