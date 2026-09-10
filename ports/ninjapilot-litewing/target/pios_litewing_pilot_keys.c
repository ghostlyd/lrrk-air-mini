#include "pios_litewing_pilot_keys.h"
#include <string.h>
#include "mbedtls/hkdf.h"
#include "mbedtls/platform_util.h"

int lw_pilot_derive_keys(const uint8_t root[32], const uint8_t host[32],
                         const uint8_t board[32], const uint8_t session[16],
                         struct lw_session_keys *out)
{
    static const char *const labels[] = {
        "LWPL/v1/c2b/", "LWPL/v1/b2c/", "LWPL/v1/telemetry/"
    };
    uint8_t salt[64] = {0};
    uint8_t info[sizeof("LWPL/v1/telemetry/") - 1 + 16] = {0};
    struct lw_session_keys keys = {0};
    uint8_t *dest[] = { keys.c2b, keys.b2c, keys.telemetry };
    int result = -1;
    if (!out) return -1;
    mbedtls_platform_zeroize(out, sizeof(*out));
    if (!root || !host || !board || !session) goto done;
    const mbedtls_md_info_t *md = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (!md) goto done;
    memcpy(salt, host, 32);
    memcpy(salt + 32, board, 32);
    for (unsigned i = 0; i < 3; ++i) {
        size_t length = strlen(labels[i]);
        memcpy(info, labels[i], length);
        memcpy(info + length, session, 16);
        if (mbedtls_hkdf(md, salt, sizeof(salt), root, 32,
                         info, length + 16, dest[i], 32) != 0) goto done;
    }
    memcpy(out, &keys, sizeof(keys));
    result = 0;
done:
    mbedtls_platform_zeroize(&keys, sizeof(keys));
    mbedtls_platform_zeroize(salt, sizeof(salt));
    mbedtls_platform_zeroize(info, sizeof(info));
    return result;
}
