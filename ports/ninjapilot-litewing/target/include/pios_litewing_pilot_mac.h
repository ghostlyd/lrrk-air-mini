#pragma once
#include <stddef.h>
#include <stdint.h>

struct lw_pilot_mac_key { uint8_t bytes[32]; };
/* Context points to a caller-selected direction key. Buffers must not overlap.
 * No provisioning/derivation occurs here. Non-null tag is cleared on failure.
 */
int lw_pilot_mac(void *ctx, const uint8_t *message, size_t length, uint8_t tag[32]);
