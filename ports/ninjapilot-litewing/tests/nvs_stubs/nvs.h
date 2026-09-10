#pragma once
#include <stddef.h>
#include <stdint.h>
typedef int esp_err_t;
typedef uint32_t nvs_handle_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NVS_NOT_FOUND 0x1102
#define ESP_ERR_NVS_INVALID_LENGTH 0x110c
#define ESP_ERR_NVS_NO_FREE_PAGES 0x110d
#define ESP_ERR_NVS_NEW_VERSION_FOUND 0x1110
#define NVS_READWRITE 1
#define NVS_READONLY 0
void nvs_close(nvs_handle_t);
typedef struct { size_t used_entries, free_entries; } nvs_stats_t;
esp_err_t nvs_open_from_partition(const char *, const char *, int, nvs_handle_t *);
esp_err_t nvs_get_u8(nvs_handle_t, const char *, uint8_t *);
esp_err_t nvs_set_u8(nvs_handle_t, const char *, uint8_t);
esp_err_t nvs_commit(nvs_handle_t);
esp_err_t nvs_get_blob(nvs_handle_t, const char *, void *, size_t *);
esp_err_t nvs_set_blob(nvs_handle_t, const char *, const void *, size_t);
esp_err_t nvs_erase_key(nvs_handle_t, const char *);
esp_err_t nvs_erase_all(nvs_handle_t);
esp_err_t nvs_get_stats(const char *, nvs_stats_t *);
