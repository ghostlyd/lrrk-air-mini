#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef int esp_err_t;
#define ESP_OK 0
typedef struct esp_netif_obj esp_netif_t;
typedef struct { uint32_t addr; } esp_ip4_addr_t;
typedef struct { esp_ip4_addr_t ip, netmask, gw; } esp_netif_ip_info_t;
esp_netif_t *esp_netif_get_handle_from_ifkey(const char *);
bool esp_netif_is_netif_up(esp_netif_t *);
esp_err_t esp_netif_get_ip_info(esp_netif_t *, esp_netif_ip_info_t *);
