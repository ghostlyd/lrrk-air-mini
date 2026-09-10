#pragma once
#include <stddef.h>
#include <stdint.h>
#include "pios_litewing_pilot_keys.h"

enum lw_session_phase { LW_CLOSED, LW_PENDING, LW_ACTIVE };
enum lw_session_result { LW_REJECT, LW_HANDSHAKE_REPLY, LW_RETIRED };
typedef int (*lw_session_rng)(void *, uint8_t *, size_t);

/* Initial admission core. Caller serializes all calls. No receiver/arming I/O.
 * ACTIVE is handshake state only; rolling challenges and PILOT are not yet
 * implemented. Without input integration it expires 100ms after challenge.
 * State, inputs, and outputs must not overlap; RNG must be a CSPRNG, return 0
 * only after filling the whole buffer, and must not reenter this API. */
struct lw_pilot_session {
    enum lw_session_phase phase;
    int64_t last_us, started_us, challenge_us;
    uint8_t session[16], challenge[16];
    struct lw_session_keys keys;
};
void lw_session_init(struct lw_pilot_session *state);
void lw_session_retire(struct lw_pilot_session *state);
int lw_session_tick(struct lw_pilot_session *state, int64_t now_us);
/* root is provisioned externally, never discovered or persisted by this core.
 * On any non-reply result, written=0. Never transmit failed-call output.
 * disarmed/owner_free must each be exactly 1 for either admission transition. */
enum lw_session_result lw_session_receive(struct lw_pilot_session *state,
    const uint8_t *wire, size_t size, const uint8_t root[32], int64_t now_us,
    int disarmed, int owner_free, lw_session_rng random, void *random_ctx,
    uint8_t *reply, size_t capacity, size_t *written);
