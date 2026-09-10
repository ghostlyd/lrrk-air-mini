#pragma once
#include <stdint.h>
#include "esp_event.h"
#include "esp_wifi_types_generic.h"
/* Only init-config is reduced: the real SDK default initializer is checked by
 * target compilation. Full wifi_config_t/AP/STA/NAN layouts use SDK headers. */
typedef struct { int nvs_enable; } wifi_init_config_t;
#define WIFI_INIT_CONFIG_DEFAULT() { .nvs_enable = 1 }
esp_err_t esp_wifi_init(const wifi_init_config_t *);
esp_err_t esp_wifi_deinit(void);
esp_err_t esp_wifi_get_mode(wifi_mode_t *);
esp_err_t esp_wifi_set_mode(wifi_mode_t);
esp_err_t esp_wifi_set_storage(wifi_storage_t);
esp_err_t esp_wifi_set_config(wifi_interface_t, wifi_config_t *);
esp_err_t esp_wifi_start(void);
esp_err_t esp_wifi_stop(void);
