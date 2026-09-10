#ifndef PIOS_LITEWING_PILOT_KEYS_H
#define PIOS_LITEWING_PILOT_KEYS_H
#include <stdint.h>

struct lw_session_keys {
    uint8_t c2b[32];
    uint8_t b2c[32];
    uint8_t telemetry[32];
};

/* Inputs must have the stated sizes and must not overlap out.
 * Returns 0 on success, -1 on failure; nonnull out clears on failure.
 * Caller owns secure retirement of successful output. No I/O or authority. */
int lw_pilot_derive_keys(const uint8_t root[32], const uint8_t host[32],
                         const uint8_t board[32], const uint8_t session[16],
                         struct lw_session_keys *out);
#endif
