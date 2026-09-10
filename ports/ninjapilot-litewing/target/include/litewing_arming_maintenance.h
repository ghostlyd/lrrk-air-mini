/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdint.h>
/* Trusted maintenance only. Nonblocking acquisition of the object-manager
 * mutex; begin atomically observes Disarmed and inhibits subsequent writes of
 * Armed/Arming. Does not disarm, change settings, or hold the mutex across work.
 * Token must remain held through credential cleanup; failed end retains it.
 * No wire endpoint. Zero/-1 for begin/end; held returns 1/0. */
int32_t lw_arming_maintenance_begin(uint64_t *token);
int32_t lw_arming_maintenance_held(uint64_t token);
int32_t lw_arming_maintenance_end(uint64_t token);
