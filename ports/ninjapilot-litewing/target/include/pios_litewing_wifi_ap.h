/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdint.h>

enum lw_wifi_ap_fault {
    LW_WIFI_AP_STOPPED = 1u << 0,
    LW_WIFI_AP_STATION_LOST = 1u << 1,
    LW_WIFI_AP_LIFECYCLE_FAILED = 1u << 2,
};

/* Singleton, called only by one trusted owning task. No concurrent lifecycle
 * calls or competing Wi-Fi/network-interface initialization are permitted.
 * Refuses an existing Wi-Fi driver or any preexisting network interface (even
 * one with a custom key); USB UART is not an esp_netif and remains unaffected.
 * A default event loop may be borrowed; a loop created here must not be adopted
 * by other components until stop completes. Global esp_netif initialization is
 * retained (IDF does not support lwIP deinitialization).
 * Wi-Fi-specific SDK log levels are saved, suppressed with readback before
 * setup and restored after cleanup. Do not concurrently change those tags.
 *
 * start loads existing credentials before any SDK network operation. Returns 0
 * only after all setup APIs, including esp_wifi_start, succeed without a latched
 * fault; this is not evidence of asynchronous IP readiness or a connected peer.
 * Otherwise returns -1 and clears root. No retained application-key copy.
 * root must point to 32 writable bytes owned exclusively by the trusted caller.
 * A duplicate start fails without altering the active lifecycle.
 *
 * stop clears the supplied root even on failure. Caller must also retire/wipe
 * any derived session keys or other copies. -1 means cleanup failed: poll faults,
 * keep control retired and retry stop; never assume the radio is off. New starts
 * are rejected while any owned resource remains. NULL root is allowed for stop.
 * Wiping is best effort and cannot erase driver/compiler copies.
 */
int lw_wifi_ap_start(uint8_t root[32]);
int lw_wifi_ap_stop(uint8_t root[32]);
/* Sticky flags, safe alongside the SDK event task; only a fresh start resets
 * them. Poll before every controller admission/ingress/tick. Callback context
 * never calls controller/receiver APIs. A fault does not itself stop the radio. */
unsigned lw_wifi_ap_faults(void);
