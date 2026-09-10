/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>

/* Trusted boot-only startup, after UAVObjects and receiver initialization.
 * Creates an optional, waiting worker; does not stop/start radio or store data.
 * The task lives until reboot. No retry after successful launch. */
int lw_usb_maintenance_start(void);
/* Trusted physical USB parser only, after frame/CRC/type/instance validation.
 * Exact 152 bytes: nonzero transaction ID[16], LWCF[136]. Copies one pending
 * request and returns immediately; 0 means queued, not persisted. Input must
 * remain stable during this call; caller owns/wipes its original buffer.
 * No authentication substitute: never expose through UDP or model tools. */
int lw_usb_maintenance_submit(const uint8_t *payload, size_t size);
/* Nonsecret 24-byte status defined by usb-provisioning-wire.md. Returns 24,
 * or -1 without writing for null/insufficient output. Snapshot, not a lease. */
int lw_usb_maintenance_status(uint8_t *out, size_t capacity);
