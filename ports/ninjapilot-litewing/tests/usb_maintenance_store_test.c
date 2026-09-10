/* Reuse actual-worker lifecycle assertions, replacing its store-result double
 * with the actual store. NVS, radio, RTOS and object-manager boundaries
 * remain simulated; generated FlightStatus setters are tested separately. */
#include <stdio.h>
#define main lifecycle_main
#define lw_wifi_config_store boundary_store_checks
#include "usb_maintenance_test.c"
#undef lw_wifi_config_store
#undef main
#include "nvs.h"
#include "nvs_flash.h"
extern enum lw_wifi_store_result lw_wifi_config_store(const uint8_t *,size_t);
static uint8_t disk[136];
static unsigned nvs_sets, nvs_commits, nvs_reads, nvs_opens, nvs_closes;
static int readback_failure, readback_mismatch, live_handle;
esp_err_t nvs_flash_init_partition(const char *part) {
    assert(!strcmp(part,"nvs"));
    return CASE("not-written") ? ESP_FAIL : ESP_OK;
}
esp_err_t nvs_open_from_partition(const char *part,const char *space,int mode,nvs_handle_t *h) {
    assert(!strcmp(part,"nvs") && !strcmp(space,"lw_pilot"));
    assert(mode==NVS_READWRITE || mode==NVS_READONLY);
    assert(!live_handle);
    if (mode==NVS_READONLY) assert(nvs_commits==1 && nvs_closes==1);
    else assert(nvs_opens==0);
    *h=mode==NVS_READWRITE ? 9 : 10; live_handle=(int)*h;
    ++nvs_opens; return ESP_OK;
}
void nvs_close(nvs_handle_t h) {
    assert((h==9 || h==10) && live_handle==(int)h);
    live_handle=0; ++nvs_closes;
}
esp_err_t nvs_set_blob(nvs_handle_t h,const char *key,const void *data,size_t size) {
    assert(h==9 && !strcmp(key,"config") && size==136);
    assert(live_handle==9);
    assert_arming_inhibited();
    assert(!memcmp(data,expected,136));
    memcpy(disk,data,136); ++nvs_sets; return ESP_OK;
}
esp_err_t nvs_commit(nvs_handle_t h) {
    assert(h==9 && nvs_sets==1); ++nvs_commits;
    assert(live_handle==9);
    return CASE("uncertain") && !readback_failure && !readback_mismatch ? ESP_FAIL : ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t h,const char *key,void *data,size_t *size) {
    assert(h==10 && !strcmp(key,"config") && *size==136);
    assert(live_handle==10);
    assert_arming_inhibited(); memcpy(data,disk,136); ++nvs_reads;
    if (readback_mismatch) ((uint8_t *)data)[8]^=1;
    return readback_failure ? ESP_FAIL : ESP_OK;
}
enum lw_wifi_store_result integrated_store(const uint8_t *blob,size_t size) {
    enum lw_wifi_store_result predicted=boundary_store_checks(blob,size);
#ifdef TEST_BYPASS_STORE
    enum lw_wifi_store_result actual=predicted;
#else
    enum lw_wifi_store_result actual=lw_wifi_config_store(blob,size);
#endif
    assert(actual==predicted); return actual;
}
int main(int argc,char **argv) {
    assert(argc==2);
    readback_failure=!strcmp(argv[1],"readback-failure");
    readback_mismatch=!strcmp(argv[1],"readback-mismatch");
    if (readback_failure || readback_mismatch) argv[1]="uncertain";
    int result=lifecycle_main(argc,argv);
    assert(nvs_opens==nvs_closes && live_handle==0);
    assert(nvs_sets==(writes && !CASE("not-written") ? 1u : 0u));
    assert(nvs_commits==nvs_sets);
    assert(nvs_reads==(nvs_sets && (!CASE("uncertain") || readback_failure || readback_mismatch) ? 1u : 0u));
    if (nvs_sets) assert(!memcmp(disk,expected,136));
    return result;
}
