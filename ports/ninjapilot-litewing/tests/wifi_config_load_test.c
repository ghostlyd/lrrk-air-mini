/* Only flash storage is replaced: decode and loader are production sources. */
#include "litewing_wifi_config.h"
#include "nvs_flash.h"
#include <assert.h>
#include <string.h>
static int failure, opened, closed, reads;
esp_err_t nvs_flash_init_partition(const char *partition) {
    assert(!strcmp(partition,"nvs"));
    return failure==1 ? ESP_ERR_NVS_NO_FREE_PAGES : ESP_OK;
}
esp_err_t nvs_open_from_partition(const char *partition,const char *space,int mode,nvs_handle_t *h) {
    assert(!strcmp(partition,"nvs") && !strcmp(space,"lw_pilot") && mode==NVS_READONLY);
    if(failure==2) return ESP_ERR_NVS_NOT_FOUND;
    *h=9; ++opened; return ESP_OK;
}
void nvs_close(nvs_handle_t h) { assert(h==9); ++closed; }
esp_err_t nvs_get_blob(nvs_handle_t h,const char *key,void *out,size_t *size) {
    assert(h==9 && !strcmp(key,"config") && out && *size==136); ++reads;
    uint8_t b[136]={'L','W','C','F',1,4,16,0};
    memset(b+8,0x42,32); memcpy(b+40,"test",4); memcpy(b+72,"fixture-key-1234",16);
    memcpy(out,b,136);
    if(failure==3) return ESP_FAIL; /* partial output must never leak */
    if(failure==4) *size=135;
    if(failure==5) ((uint8_t *)out)[4]=2;
    return ESP_OK;
}
/* Deliberately no erase, set, commit or radio API: a call fails linkage. */
int main(void) {
    struct lw_wifi_config c;
    for(failure=0;failure<=5;++failure) {
        opened=closed=reads=0; memset(&c,0xaa,sizeof(c));
        int result=lw_wifi_config_load(&c);
        assert(opened==closed);
        assert(reads==(failure==1 || failure==2 ? 0 : 1));
        if(!failure) {
            assert(result==0 && !strcmp(c.ssid,"test") && !strcmp(c.password,"fixture-key-1234"));
            for(size_t i=0;i<32;++i) assert(c.root[i]==0x42);
        } else {
            assert(result!=0);
            const unsigned char *p=(const unsigned char *)&c;
            for(size_t i=0;i<sizeof(c);++i) assert(p[i]==0);
        }
    }
    assert(lw_wifi_config_load(NULL)!=0);
    return 0;
}
