/* Test-only fault injection around the real session crypto dependencies. */
#include "pios_litewing_pilot_keys.h"
#include "pios_litewing_pilot_mac.h"
#include <string.h>
static int fail_kdf, fail_mac_at, mac_calls;
void session_faults(int kdf, int mac)
{
    fail_kdf = kdf;
    fail_mac_at = mac;
    mac_calls = 0;
}
static int checked_keys(const uint8_t root[32], const uint8_t host[32],
    const uint8_t board[32], const uint8_t session[16], struct lw_session_keys *out)
{
    if (fail_kdf) {
        memset(out, 0xa5, sizeof(*out));
        return -1;
    }
    return lw_pilot_derive_keys(root, host, board, session, out);
}
static int checked_mac(void *ctx, const uint8_t *message, size_t size, uint8_t tag[32])
{
    if (++mac_calls == fail_mac_at) {
        memset(tag, 0xa5, 32);
        return -1;
    }
    return lw_pilot_mac(ctx, message, size, tag);
}
#define lw_pilot_derive_keys checked_keys
#define lw_pilot_mac checked_mac
#include "../target/litewing_pilot_session.c"
