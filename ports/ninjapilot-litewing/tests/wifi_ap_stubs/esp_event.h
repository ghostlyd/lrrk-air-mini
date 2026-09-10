/* Host-only SDK boundary; Wi-Fi data types come from pinned SDK headers. */
#pragma once
#include <stdint.h>
#include "esp_event_base.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_WIFI_NOT_INIT 0x3001
#define ESP_ERR_WIFI_NOT_STARTED 0x3002
typedef void *esp_event_handler_instance_t;
esp_err_t esp_event_loop_create_default(void);
esp_err_t esp_event_loop_delete_default(void);
esp_err_t esp_event_handler_instance_register(esp_event_base_t, int32_t,
    esp_event_handler_t, void *, esp_event_handler_instance_t *);
esp_err_t esp_event_handler_instance_unregister(esp_event_base_t, int32_t,
    esp_event_handler_instance_t);
