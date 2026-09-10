#pragma once
#include "../../gcs_stubs/freertos/FreeRTOS.h"
#include <stdint.h>
typedef int BaseType_t;
typedef unsigned UBaseType_t;
typedef uint32_t TickType_t;
#define pdPASS 1
#define tskIDLE_PRIORITY 0
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))
