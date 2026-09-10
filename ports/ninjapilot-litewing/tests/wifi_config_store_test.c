/* Real store/decoder, only NVS replaced. No erase or radio symbol provided. */
#include "litewing_wifi_store.h"
#include "litewing_wifi_config.h"
#include "nvs_flash.h"
#include <assert.h>
#include <string.h>

static int failure, init_calls, opens, closes, sets, commits, reads;
static uint8_t disk[136], original[136], expected[136];
static int mutate_input;

static void reset(int mode) {
    failure=mode; init_calls=opens=closes=sets=commits=reads=0;
    mutate_input=0;
    memset(original,0,sizeof(original));
    memcpy(original,"LWCF",4); original[4]=1; original[5]=4; original[6]=16;
    memset(original+8,0x42,32); memcpy(original+40,"test",4);
    memcpy(original+72,"fixture-key-1234",16);
    memcpy(expected,original,sizeof(expected));
}
esp_err_t nvs_flash_init_partition(const char *part) {
    assert(!strcmp(part,"nvs")); ++init_calls;
    return failure==1 ? ESP_ERR_NVS_NO_FREE_PAGES : ESP_OK;
}
esp_err_t nvs_open_from_partition(const char *part,const char *space,int mode,nvs_handle_t *h) {
    assert(!strcmp(part,"nvs") && !strcmp(space,"lw_pilot"));
    if(mode==NVS_READWRITE) {
        assert(sets==0 && commits==0 && closes==0);
        if(failure==2) return ESP_FAIL;
        *h=9;
    } else {
        assert(mode==NVS_READONLY && commits==1 && closes==1);
        if(failure==5) return ESP_FAIL;
        *h=10;
    }
    ++opens; return ESP_OK;
}
void nvs_close(nvs_handle_t h) {
    assert(h==9 || h==10); assert(closes<opens); ++closes;
}
esp_err_t nvs_set_blob(nvs_handle_t h,const char *key,const void *blob,size_t size) {
    assert(h==9 && !strcmp(key,"config") && size==136 && sets==0);
    assert(blob!=original && !memcmp(blob,expected,136));
    ++sets;
    if(mutate_input) memset(original,0xcc,sizeof(original));
    memcpy(disk,blob,136);
    return failure==3 ? ESP_FAIL : ESP_OK;
}
esp_err_t nvs_commit(nvs_handle_t h) {
    assert(h==9 && sets==1 && commits==0 && closes==0); ++commits;
    return failure==4 ? ESP_FAIL : ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t h,const char *key,void *blob,size_t *size) {
    assert(h==10 && !strcmp(key,"config") && *size==136 && commits==1);
    ++reads; memcpy(blob,disk,136);
    if(failure==6) return ESP_FAIL;
    if(failure==7) *size=135;
    if(failure==8) { *size=4096; return ESP_ERR_NVS_INVALID_LENGTH; }
    if(failure==9) ((uint8_t *)blob)[8]^=1;
    return ESP_OK;
}
int main(void) {
    for(int mode=0;mode<=9;++mode) {
        reset(mode);
        enum lw_wifi_store_result result=lw_wifi_config_store(original,136);
        assert(result==(mode==0 ? LW_WIFI_STORE_VERIFIED :
                       mode<=2 ? LW_WIFI_STORE_NOT_WRITTEN : LW_WIFI_STORE_UNCERTAIN));
        assert(opens==closes);
        assert(sets==(mode==1 || mode==2 ? 0 : 1));
        assert(commits==(mode>=1 && mode<=3 ? 0 : 1));
        assert(reads==(mode>=1 && mode<=5 ? 0 : 1));
        if(mode>=3) {
            reset(0); /* retry the same credential bytes after uncertain outcome */
            assert(lw_wifi_config_store(original,136)==LW_WIFI_STORE_VERIFIED);
            assert(!memcmp(disk,expected,136));
        }
    }
    reset(0); mutate_input=1;
    assert(lw_wifi_config_store(original,136)==LW_WIFI_STORE_VERIFIED);
    assert(!memcmp(disk,expected,136));
    reset(0);
    assert(lw_wifi_config_store(NULL,136)==LW_WIFI_STORE_INVALID);
    assert(lw_wifi_config_store(original,135)==LW_WIFI_STORE_INVALID);
    assert(lw_wifi_config_store(original,137)==LW_WIFI_STORE_INVALID);
    original[4]=2;
    assert(lw_wifi_config_store(original,136)==LW_WIFI_STORE_INVALID);
    assert(init_calls==0 && opens==0 && sets==0);
    return 0;
}
