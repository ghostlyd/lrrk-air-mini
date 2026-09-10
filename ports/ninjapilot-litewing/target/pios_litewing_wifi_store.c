/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "litewing_wifi_store.h"
#include "litewing_wifi_config.h"
#include <nvs.h>
#include <nvs_flash.h>
#include <string.h>

static void wipe_bytes(uint8_t *bytes, size_t size)
{
    volatile uint8_t *out=bytes;
    for (size_t i=0;i<size;++i) out[i]=0;
}

enum lw_wifi_store_result lw_wifi_config_store(const uint8_t *blob, size_t size)
{
    if (!blob || size!=LW_WIFI_CONFIG_SIZE) return LW_WIFI_STORE_INVALID;
    uint8_t snapshot[LW_WIFI_CONFIG_SIZE], readback[LW_WIFI_CONFIG_SIZE]={0};
    struct lw_wifi_config decoded;
    memcpy(snapshot,blob,sizeof(snapshot));
    enum lw_wifi_store_result result=LW_WIFI_STORE_INVALID;
    nvs_handle_t handle=0;
    int opened=0;
    if (lw_wifi_config_decode(snapshot,sizeof(snapshot),&decoded)!=0) goto end;
    result=LW_WIFI_STORE_NOT_WRITTEN;
    if (nvs_flash_init_partition("nvs")!=ESP_OK) goto end;
    if (nvs_open_from_partition("nvs","lw_pilot",NVS_READWRITE,&handle)!=ESP_OK)
        goto end;
    opened=1;
    result=LW_WIFI_STORE_UNCERTAIN;
    if (nvs_set_blob(handle,"config",snapshot,sizeof(snapshot))!=ESP_OK) goto end;
    if (nvs_commit(handle)!=ESP_OK) goto end;
    nvs_close(handle); opened=0;
    if (nvs_open_from_partition("nvs","lw_pilot",NVS_READONLY,&handle)!=ESP_OK)
        goto end;
    opened=1;
    size_t stored_size=sizeof(readback);
    if (nvs_get_blob(handle,"config",readback,&stored_size)!=ESP_OK ||
        stored_size!=sizeof(readback)) goto end;
    unsigned difference=0;
    for (size_t i=0;i<sizeof(snapshot);++i) difference|=snapshot[i]^readback[i];
    if (!difference) result=LW_WIFI_STORE_VERIFIED;
end:
    if (opened) nvs_close(handle);
    lw_wifi_config_clear(&decoded);
    wipe_bytes(snapshot,sizeof(snapshot));
    wipe_bytes(readback,sizeof(readback));
    return result;
}
