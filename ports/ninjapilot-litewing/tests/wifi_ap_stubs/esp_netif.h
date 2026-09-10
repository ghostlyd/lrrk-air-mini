#pragma once
#include <stddef.h>
#include "esp_event.h"
typedef struct esp_netif_obj esp_netif_t;
typedef struct {
    const void *base;
    const void *driver;
    const void *stack;
} esp_netif_config_t;
extern const int fixture_ap_base, fixture_ap_stack;
#define ESP_NETIF_DEFAULT_WIFI_AP() { &fixture_ap_base, NULL, &fixture_ap_stack }
esp_err_t esp_netif_init(void);
size_t esp_netif_get_nr_of_ifs(void);
esp_netif_t *esp_netif_new(const esp_netif_config_t *);
void esp_netif_destroy(esp_netif_t *);
