/* SPDX-License-Identifier: GPL-3.0-or-later
 * Catch unsafe credential handoff, open/flash-backed AP setup, lost events,
 * borrowed-resource destruction and forgotten ownership after SDK errors. */
#include "pios_litewing_wifi_ap.h"
#include "litewing_wifi_config.h"
#include "esp_wifi.h"
#include "esp_wifi_default.h"
#include "nvs.h"
#include "esp_log.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>

ESP_EVENT_DEFINE_BASE(WIFI_EVENT);
const int fixture_ap_base = 1, fixture_ap_stack = 2;
struct esp_netif_obj { int unused; } owned_netif;
enum operation { NONE, NET_INIT, LOOP_CREATE, NET_NEW, ATTACH, DEFAULT_HANDLERS,
    WIFI_INIT, STORAGE, MODE, CONFIG, REGISTER, START, STOP, DEINIT, UNREGISTER,
    CLEAR, LOOP_DELETE, PROBE, LOG_QUIET, LOG_RESTORE };
static enum operation fail, fail_second;
static int initialized, running, loop, ours, netif, attached, defaults, registered;
static int ram_storage, ap_mode, configured;
static int borrowed, load_error, bad_blob, network_calls, starts, emit_at_start;
static int nvs_error, key_error, max_credentials;
static esp_event_handler_t callback;
static void *callback_arg;
static uint8_t blob[136];
static wifi_config_t driver_config;
static const char *const log_tags[] = {
    "wifi", "wifi_init_default", "esp_netif_lwip", "wpa", "pp", "net80211", "core", "target"
};
static esp_log_level_t levels[8];
static int hit(enum operation op) { ++network_calls; return fail == op || fail_second == op; }
static size_t log_index(const char *tag) {
    for (size_t i = 0; i < 8; ++i) if (!strcmp(tag, log_tags[i])) return i;
    assert(!"must not change USB/global log policy"); return 0;
}
void esp_log_level_set(const char *tag, esp_log_level_t level) {
    if (!hit(level == ESP_LOG_NONE ? LOG_QUIET : LOG_RESTORE)) levels[log_index(tag)] = level;
}
esp_log_level_t esp_log_level_get(const char *tag) { return levels[log_index(tag)]; }
static void zero(const uint8_t *p, size_t n) {
    for (size_t i = 0; i < n; ++i) assert(p[i] == 0);
}
static void credentials(void) {
    memset(blob, 0, sizeof(blob));
    memcpy(blob, "LWCF", 4); blob[4] = 1;
    blob[5] = max_credentials ? 32 : 7;
    blob[6] = max_credentials ? 63 : 16;
    memset(blob + 8, 0x39, 32);
    if (max_credentials) {
        memset(blob + 40, 'S', 32); memset(blob + 72, 'P', 63);
    } else {
        memcpy(blob + 40, "test-ap", 7);
        memcpy(blob + 72, "test-only-passwd", 16);
    }
    if (bad_blob) blob[4] = 2;
}
esp_err_t nvs_flash_init_partition(const char *p) {
    assert(!strcmp(p, "nvs")); return load_error ? ESP_FAIL : ESP_OK;
}
esp_err_t nvs_open_from_partition(const char *p, const char *n, int mode, nvs_handle_t *h) {
    assert(!strcmp(p, "nvs") && !strcmp(n, "lw_pilot") && mode == NVS_READONLY);
    *h = 7; return nvs_error ? ESP_FAIL : ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t h, const char *key, void *out, size_t *size) {
    assert(h == 7 && !strcmp(key, "config") && *size == 136);
    credentials(); memcpy(out, blob, 136); return key_error ? ESP_ERR_NVS_NOT_FOUND : ESP_OK;
}
void nvs_close(nvs_handle_t h) { assert(h == 7); }
esp_err_t esp_wifi_get_mode(wifi_mode_t *m) {
    *m = WIFI_MODE_AP; if (hit(PROBE)) return ESP_FAIL;
    return initialized ? ESP_OK : ESP_ERR_WIFI_NOT_INIT;
}
esp_err_t esp_netif_init(void) { return hit(NET_INIT) ? ESP_FAIL : ESP_OK; }
size_t esp_netif_get_nr_of_ifs(void) { ++network_calls; return borrowed ? 1 : 0; }
esp_err_t esp_event_loop_create_default(void) {
    if (hit(LOOP_CREATE)) return ESP_FAIL;
    if (loop) return ESP_ERR_INVALID_STATE;
    loop = ours = 1; return ESP_OK;
}
esp_err_t esp_event_loop_delete_default(void) {
    assert(loop && ours && !netif && !registered && !initialized);
    if (hit(LOOP_DELETE)) return ESP_FAIL;
    loop = ours = 0; return ESP_OK;
}
esp_netif_t *esp_netif_new(const esp_netif_config_t *c) {
    assert(c->base == &fixture_ap_base && c->stack == &fixture_ap_stack && !c->driver);
    if (hit(NET_NEW)) return NULL;
    assert(!netif); netif = 1; return &owned_netif;
}
void esp_netif_destroy(esp_netif_t *n) {
    assert(n == &owned_netif && netif && !attached && !defaults && !running);
    netif = 0;
}
esp_err_t esp_netif_attach_wifi_ap(esp_netif_t *n) {
    assert(n == &owned_netif && netif);
    for (size_t i = 0; i < 8; ++i) assert(levels[i] == ESP_LOG_NONE);
    /* SDK records the AP pointer before allocation, even on attach failure. */
    attached = 1; return hit(ATTACH) ? ESP_FAIL : ESP_OK;
}
esp_err_t esp_wifi_set_default_wifi_ap_handlers(void) {
    assert(attached && loop);
    if (hit(DEFAULT_HANDLERS)) return ESP_FAIL;
    defaults = 1; return ESP_OK;
}
esp_err_t esp_wifi_clear_default_wifi_driver_and_handlers(void *n) {
    assert(n == &owned_netif && !running);
    /* SDK consumes driver even if its return status is an error. */
    attached = defaults = 0; return hit(CLEAR) ? ESP_FAIL : ESP_OK;
}
esp_err_t esp_wifi_init(const wifi_init_config_t *c) {
    assert(!initialized && c->nvs_enable == 0);
    if (hit(WIFI_INIT)) return ESP_FAIL;
    initialized = 1; return ESP_OK;
}
esp_err_t esp_wifi_set_storage(wifi_storage_t s) {
    assert(initialized && !running && s == WIFI_STORAGE_RAM);
    if (hit(STORAGE)) return ESP_FAIL;
    ram_storage = 1; return ESP_OK;
}
esp_err_t esp_wifi_set_mode(wifi_mode_t m) {
    assert(initialized && ram_storage && !running && m == WIFI_MODE_AP);
    if (hit(MODE)) return ESP_FAIL;
    ap_mode = 1; return ESP_OK;
}
esp_err_t esp_wifi_set_config(wifi_interface_t i, wifi_config_t *c) {
    assert(initialized && ram_storage && ap_mode && i == WIFI_IF_AP && !running);
    assert(c->ap.ssid_len == (max_credentials ? 32 : 7));
    assert(!memcmp(c->ap.ssid, blob + 40, c->ap.ssid_len));
    assert(!memcmp(c->ap.password, blob + 72, 64));
    assert(c->ap.authmode == WIFI_AUTH_WPA2_PSK && c->ap.max_connection == 1);
    assert(c->ap.pmf_cfg.capable && !c->ap.pmf_cfg.required);
    assert(c->ap.pairwise_cipher == WIFI_CIPHER_TYPE_CCMP);
    assert(c->ap.channel == 1 && c->ap.beacon_interval == 100);
    driver_config = *c;
    if (hit(CONFIG)) return ESP_FAIL;
    configured = 1; return ESP_OK;
}
esp_err_t esp_event_handler_instance_register(esp_event_base_t base, int32_t id,
    esp_event_handler_t cb, void *arg, esp_event_handler_instance_t *instance) {
    assert(base == WIFI_EVENT && id == ESP_EVENT_ANY_ID && !registered);
    if (hit(REGISTER)) return ESP_FAIL;
    registered = 1; callback = cb; callback_arg = arg; *instance = &registered; return ESP_OK;
}
esp_err_t esp_event_handler_instance_unregister(esp_event_base_t base, int32_t id,
    esp_event_handler_instance_t instance) {
    assert(base == WIFI_EVENT && id == ESP_EVENT_ANY_ID && instance == &registered);
    assert(registered && !running);
    if (hit(UNREGISTER)) return ESP_FAIL;
    registered = 0; callback = NULL; return ESP_OK;
}
esp_err_t esp_wifi_start(void) {
    assert(initialized && defaults && registered && ram_storage && ap_mode && configured);
    ++starts; running = 1; /* failure may still require stop */
    if (emit_at_start) callback(callback_arg, WIFI_EVENT, WIFI_EVENT_AP_STOP, NULL);
    return hit(START) ? ESP_FAIL : ESP_OK;
}
esp_err_t esp_wifi_stop(void) {
    assert(initialized);
    if (hit(STOP)) return ESP_FAIL;
    if (!running) return ESP_ERR_WIFI_NOT_STARTED;
    running = 0;
    if (registered) callback(callback_arg, WIFI_EVENT, WIFI_EVENT_AP_STOP, NULL);
    return ESP_OK;
}
esp_err_t esp_wifi_deinit(void) {
    assert(initialized && !running);
    if (hit(DEINIT)) return ESP_FAIL;
    initialized = ram_storage = ap_mode = configured = 0;
    memset(&driver_config, 0, sizeof(driver_config)); return ESP_OK;
}
static void clean(void) {
    assert(!initialized && !running && !netif && !attached && !defaults && !registered);
}
static void *events(void *unused) {
    (void)unused;
    for (int i = 0; i < 10000; ++i)
        callback(callback_arg, WIFI_EVENT, WIFI_EVENT_AP_STADISCONNECTED, NULL);
    return NULL;
}
int main(void) {
    uint8_t root[32];
    for (size_t i = 0; i < 8; ++i) levels[i] = ESP_LOG_INFO;
    /* Bad/missing credentials must not reach any SDK network API. */
    for (int i = 0; i < 4; ++i) {
        load_error = i == 0; bad_blob = i == 1; nvs_error = i == 2; key_error = i == 3;
        memset(root, 0xa5, 32); network_calls = 0;
        assert(lw_wifi_ap_start(root) == -1); zero(root, 32); assert(!network_calls); clean();
    }
    load_error = bad_blob = nvs_error = key_error = 0;
    assert(lw_wifi_ap_start(NULL) == -1);
    /* Every fallible setup API must deny key handoff and unwind ownership. */
    const enum operation setup[] = {PROBE, NET_INIT, LOOP_CREATE, NET_NEW, ATTACH,
        DEFAULT_HANDLERS, WIFI_INIT, STORAGE, MODE, CONFIG, REGISTER, START, LOG_QUIET};
    for (size_t i = 0; i < sizeof(setup)/sizeof(setup[0]); ++i) {
        fail = setup[i]; memset(root, 0xa5, 32);
        assert(lw_wifi_ap_start(root) == -1); zero(root, 32); clean(); assert(!loop);
        fail = NONE; assert(lw_wifi_ap_stop(root) == 0);
        for (size_t j = 0; j < 8; ++j) assert(levels[j] == ESP_LOG_INFO);
    }
    /* Refuse preexisting Wi-Fi/default netifs without taking ownership. */
    initialized = 1;
    assert(lw_wifi_ap_start(root) == -1); assert(initialized && !loop); initialized = 0;
    for (borrowed = 1; borrowed <= 3; ++borrowed) {
        assert(lw_wifi_ap_start(root) == -1); zero(root, 32); clean();
    }
    borrowed = 0;
    /* Success hands off decoded key, borrowed loop survives, bounded extremes. */
    loop = 1;
    for (max_credentials = 0; max_credentials <= 1; ++max_credentials) {
        assert(lw_wifi_ap_start(root) == 0 && running);
        for (size_t i = 0; i < 32; ++i) assert(root[i] == 0x39);
        assert(lw_wifi_ap_faults() == 0);
        int before = starts;
        uint8_t duplicate[32];
        assert(lw_wifi_ap_start(duplicate) == -1); zero(duplicate, 32); assert(starts == before);
        callback(callback_arg, WIFI_EVENT, WIFI_EVENT_AP_STACONNECTED, NULL);
        callback(callback_arg, "unrelated", WIFI_EVENT_AP_STOP, NULL);
        assert(lw_wifi_ap_faults() == 0);
        pthread_t thread; assert(pthread_create(&thread, NULL, events, NULL) == 0);
        for (int i = 0; i < 10000; ++i) (void)lw_wifi_ap_faults();
        assert(pthread_join(thread, NULL) == 0);
        assert(lw_wifi_ap_faults() == LW_WIFI_AP_STATION_LOST && running);
        callback(callback_arg, WIFI_EVENT, WIFI_EVENT_AP_STOP, NULL);
        assert(lw_wifi_ap_faults() == (LW_WIFI_AP_STOPPED | LW_WIFI_AP_STATION_LOST));
        assert(lw_wifi_ap_stop(root) == 0); zero(root, 32); clean(); assert(loop && !ours);
        assert(lw_wifi_ap_faults() == (LW_WIFI_AP_STOPPED | LW_WIFI_AP_STATION_LOST));
    }
    max_credentials = 0; loop = 0;
    /* A start error followed by cleanup error cannot lose remaining ownership. */
    fail = START; fail_second = STOP;
    assert(lw_wifi_ap_start(root) == -1); zero(root, 32); assert(running && netif);
    assert(lw_wifi_ap_start(root) == -1);
    fail = fail_second = NONE;
    assert(lw_wifi_ap_stop(root) == 0); clean(); assert(!loop);
    /* Every setup error must also preserve a borrowed default loop. */
    loop = 1;
    for (size_t i = 0; i < sizeof(setup)/sizeof(setup[0]); ++i) {
        fail = setup[i];
        assert(lw_wifi_ap_start(root) == -1); zero(root, 32); clean(); assert(loop && !ours);
    }
    fail = NONE; loop = 0;
    emit_at_start = 1;
    assert(lw_wifi_ap_start(root) == -1); zero(root, 32); clean(); emit_at_start = 0;
    /* Failed cleanup must retain retryable resources and forbid new starts. */
    const enum operation teardown[] = {STOP, DEINIT, UNREGISTER, LOOP_DELETE, LOG_RESTORE};
    for (size_t i = 0; i < sizeof(teardown)/sizeof(teardown[0]); ++i) {
        assert(lw_wifi_ap_start(root) == 0);
        fail = teardown[i]; assert(lw_wifi_ap_stop(root) == -1); zero(root, 32);
        assert(lw_wifi_ap_faults() & LW_WIFI_AP_LIFECYCLE_FAILED);
        assert(lw_wifi_ap_start(root) == -1); zero(root, 32);
        fail = NONE; assert(lw_wifi_ap_stop(root) == 0); clean(); assert(!loop);
    }
    assert(lw_wifi_ap_start(root) == 0); fail = CLEAR;
    assert(lw_wifi_ap_stop(root) == -1); zero(root, 32); clean();
    fail = NONE; assert(lw_wifi_ap_stop(NULL) == 0);
    puts("wifi AP lifecycle: credentials, setup failures, ownership, events, teardown retry passed");
    return 0;
}
