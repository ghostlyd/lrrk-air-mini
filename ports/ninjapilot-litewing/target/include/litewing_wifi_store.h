/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>

enum lw_wifi_store_result {
    LW_WIFI_STORE_INVALID = -2,
    LW_WIFI_STORE_NOT_WRITTEN = -1,
    LW_WIFI_STORE_UNCERTAIN = 0,
    LW_WIFI_STORE_VERIFIED = 1
};
/* Internal maintenance backend, not a command authorization boundary.
 * Caller must serialize access, reserve receiver ingress, establish Disarmed,
 * stop/join radio service, and hold that exclusion throughout this operation.
 * Input must remain stable during the initial copy; caller wipes its own copy.
 * NOT_WRITTEN means no credential set was attempted. Any later error is
 * UNCERTAIN. VERIFIED means commit plus exact internal readback, not proven
 * power-loss durability. No erase, secret logging, radio start, or reset.
 */
enum lw_wifi_store_result lw_wifi_config_store(const uint8_t *blob, size_t size);
