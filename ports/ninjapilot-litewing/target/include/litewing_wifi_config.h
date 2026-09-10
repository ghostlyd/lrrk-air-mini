/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>

#define LW_WIFI_CONFIG_SIZE 136
struct lw_wifi_config {
    char ssid[33];
    char password[64];
    uint8_t root[32];
};
/* Serialized v1 blob: LWCF, version, SSID length, password length, reserved;
 * root[32], SSID[32], password[64]. Unused bytes are zero. No struct casting.
 * Input/output must not overlap. Failure clears all output, including secrets.
 * Validation cannot establish entropy or uniqueness: provisioning must use a
 * CSPRNG and generate independent application and AP credentials. */
int lw_wifi_config_decode(const uint8_t *blob, size_t size, struct lw_wifi_config *out);
void lw_wifi_config_clear(struct lw_wifi_config *config);
/* Read-only namespace access after NVS initialization. Never erases on error.
 * No radio activation, settings write, or provisioning. Call before Wi-Fi init.
 * Board storage is not claimed encrypted by this loader. */
int lw_wifi_config_load(struct lw_wifi_config *out);
