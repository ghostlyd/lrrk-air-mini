/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "litewing_wifi_config.h"
#include <nvs.h>
#include <nvs_flash.h>

int lw_wifi_config_load(struct lw_wifi_config *out)
{
    if (!out) return -1;
    lw_wifi_config_clear(out);
    /* Unlike common SDK examples, never erase an incompatible/full partition. */
    if (nvs_flash_init_partition("nvs")!=ESP_OK) return -1;
    nvs_handle_t handle;
    if (nvs_open_from_partition("nvs","lw_pilot",NVS_READONLY,&handle)!=ESP_OK)
        return -1;
    uint8_t blob[LW_WIFI_CONFIG_SIZE]={0};
    size_t size=sizeof(blob);
    esp_err_t result=nvs_get_blob(handle,"config",blob,&size);
    nvs_close(handle);
    int decoded=-1;
    if (result==ESP_OK) decoded=lw_wifi_config_decode(blob,size,out);
    volatile uint8_t *wipe=blob;
    for (size_t i=0;i<sizeof(blob);++i) wipe[i]=0;
    return decoded;
}
