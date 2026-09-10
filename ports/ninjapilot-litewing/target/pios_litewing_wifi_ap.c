/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "pios_litewing_wifi_ap.h"
#include "litewing_wifi_config.h"
#include <esp_event.h>
#include <esp_log.h>
#include <esp_netif.h>
#include <esp_wifi.h>
#include <esp_wifi_default.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stddef.h>
#include <string.h>

/* Stable callback storage, including when unregister fails. Only faults is
 * accessed by the event task; the owning task serializes all other state. */
static atomic_uint faults;
static esp_netif_t *ap_netif;
static esp_event_handler_instance_t fault_handler;
static bool own_loop, own_wifi, attach_attempted, start_attempted;
/* Pinned SDK wifi_default/netif MAC logs and Wi-Fi library printf tags.
 * Do not change wildcard/master levels or USB/flight logging. The owner must
 * exclude competing changes to these tags until teardown completes. */
static const char *const private_log_tags[] = {
    "wifi", "wifi_init_default", "esp_netif_lwip", "wpa",
    "pp", "net80211", "core", "target"
};
static esp_log_level_t saved_log_levels[sizeof(private_log_tags) / sizeof(private_log_tags[0])];
static size_t quiet_tags;

static void wipe(void *data, size_t size)
{
    volatile unsigned char *p = data;
    if (p) while (size--) *p++ = 0;
}

static void latch(unsigned bits)
{
    atomic_fetch_or_explicit(&faults, bits, memory_order_relaxed);
}

unsigned lw_wifi_ap_faults(void)
{
    return atomic_load_explicit(&faults, memory_order_relaxed);
}

static void ap_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    (void)data;
    if (base != WIFI_EVENT) return;
    if (id == WIFI_EVENT_AP_STOP) latch(LW_WIFI_AP_STOPPED);
    if (id == WIFI_EVENT_AP_STADISCONNECTED) latch(LW_WIFI_AP_STATION_LOST);
}

static bool resources_owned(void)
{
    return own_loop || own_wifi || ap_netif || fault_handler || quiet_tags;
}

int lw_wifi_ap_stop(uint8_t root[32])
{
    wipe(root, 32);
    /* Keep dependencies alive if the radio cannot be stopped/deinitialized.
     * Retry from the remaining ownership state, never from a clean fiction. */
    if (start_attempted) {
        esp_err_t err = esp_wifi_stop();
        if (err != ESP_OK && err != ESP_ERR_WIFI_NOT_STARTED) goto failed;
        start_attempted = false;
    }
    if (own_wifi) {
        if (esp_wifi_deinit() != ESP_OK) goto failed;
        own_wifi = false;
    }
    if (fault_handler) {
        if (esp_event_handler_instance_unregister(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                                  fault_handler) != ESP_OK)
            goto failed;
        fault_handler = NULL;
    }
    int result = 0;
    if (ap_netif) {
        if (attach_attempted) {
            /* IDF 5.3.2 consumes the driver even on an error return. The AP
             * slot is populated BEFORE attachment can fail, so clear it too. */
            if (esp_wifi_clear_default_wifi_driver_and_handlers(ap_netif) != ESP_OK)
                result = -1;
            attach_attempted = false;
        }
        esp_netif_destroy(ap_netif);
        ap_netif = NULL;
    }
    if (own_loop) {
        if (esp_event_loop_delete_default() != ESP_OK) goto failed;
        own_loop = false;
    }
    while (quiet_tags) {
        size_t i = quiet_tags - 1;
        esp_log_level_set(private_log_tags[i], saved_log_levels[i]);
        if (esp_log_level_get(private_log_tags[i]) != saved_log_levels[i]) goto failed;
        --quiet_tags;
    }
    if (result) latch(LW_WIFI_AP_LIFECYCLE_FAILED);
    return result;
failed:
    latch(LW_WIFI_AP_LIFECYCLE_FAILED);
    return -1;
}

int lw_wifi_ap_start(uint8_t root[32])
{
    wipe(root, 32);
    if (!root || resources_owned()) return -1;

    struct lw_wifi_config credentials = {0};
    wifi_config_t config = {0};
    int result = -1;
    /* The real loader validates lengths, terminators, text, padding and key.
     * No SDK network call, including global init, precedes this boundary. */
    if (lw_wifi_config_load(&credentials) != 0) goto done;

    /* esp_wifi_init is idempotent, not an ownership-acquisition API. Do not
     * borrow a driver's mode, storage, credentials or associated interfaces. */
    wifi_mode_t mode;
    if (esp_wifi_get_mode(&mode) != ESP_ERR_WIFI_NOT_INIT) goto done;
    if (esp_netif_init() != ESP_OK) goto failed;
    /* Default Wi-Fi attachment slots are private SDK globals. Interface keys
     * can be customized, so checking only WIFI_AP_DEF cannot prove ownership.
     * This UART + AP adapter conservatively refuses ALL preexisting netifs. */
    if (esp_netif_get_nr_of_ifs() != 0) goto done;

    atomic_store_explicit(&faults, 0, memory_order_relaxed);
    for (size_t i = 0; i < sizeof(private_log_tags) / sizeof(private_log_tags[0]); ++i) {
        saved_log_levels[i] = esp_log_level_get(private_log_tags[i]);
        quiet_tags = i + 1;
        /* esp_log_level_set returns void and can silently fail allocation. */
        esp_log_level_set(private_log_tags[i], ESP_LOG_NONE);
        if (esp_log_level_get(private_log_tags[i]) != ESP_LOG_NONE) goto failed;
    }
    esp_err_t err = esp_event_loop_create_default();
    if (err == ESP_OK) own_loop = true;
    else if (err != ESP_ERR_INVALID_STATE) goto failed;

    /* Do not use esp_netif_create_default_wifi_ap: it asserts/aborts on
     * allocation, attach and handler failures in the pinned SDK. */
    esp_netif_config_t netif_config = ESP_NETIF_DEFAULT_WIFI_AP();
    ap_netif = esp_netif_new(&netif_config);
    if (!ap_netif) goto failed;
    attach_attempted = true;
    if (esp_netif_attach_wifi_ap(ap_netif) != ESP_OK) goto failed;
    if (esp_wifi_set_default_wifi_ap_handlers() != ESP_OK) goto failed;

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    init.nvs_enable = 0;
    if (esp_wifi_init(&init) != ESP_OK) goto failed;
    own_wifi = true;
    if (esp_wifi_set_storage(WIFI_STORAGE_RAM) != ESP_OK) goto failed;
    if (esp_wifi_set_mode(WIFI_MODE_AP) != ESP_OK) goto failed;

    /* Decoder guarantees NUL termination; bounded copies also handle a full
     * 32-byte SSID. Root is never part of the SDK's Wi-Fi configuration. */
    size_t ssid_len = 0;
    while (ssid_len < sizeof(config.ap.ssid) && credentials.ssid[ssid_len]) ++ssid_len;
    memcpy(config.ap.ssid, credentials.ssid, ssid_len);
    config.ap.ssid_len = (uint8_t)ssid_len;
    memcpy(config.ap.password, credentials.password, sizeof(config.ap.password));
    config.ap.channel = 1;
    config.ap.authmode = WIFI_AUTH_WPA2_PSK;
    config.ap.max_connection = 1;
    config.ap.beacon_interval = 100;
    config.ap.pairwise_cipher = WIFI_CIPHER_TYPE_CCMP;
    config.ap.pmf_cfg.capable = true;
    config.ap.pmf_cfg.required = false;
    if (esp_wifi_set_config(WIFI_IF_AP, &config) != ESP_OK) goto failed;
    if (esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, ap_event,
                                            NULL, &fault_handler) != ESP_OK)
        goto failed;
    start_attempted = true;
    if (esp_wifi_start() != ESP_OK || lw_wifi_ap_faults()) goto failed;
    memcpy(root, credentials.root, 32);
    result = 0;
    goto done;
failed:
    latch(LW_WIFI_AP_LIFECYCLE_FAILED);
    (void)lw_wifi_ap_stop(root);
done:
    lw_wifi_config_clear(&credentials);
    wipe(&config, sizeof(config));
    return result;
}
