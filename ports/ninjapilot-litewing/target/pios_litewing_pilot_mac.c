#include "pios_litewing_pilot_mac.h"
#include "mbedtls/md.h"
#include <string.h>

int lw_pilot_mac(void *ctx, const uint8_t *message, size_t length, uint8_t tag[32])
{
    if (!tag) return -1;
    memset(tag, 0, 32);
    if (!ctx || !message) return -1;
    const struct lw_pilot_mac_key *key = ctx;
    const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (!info) return -1;
    if (mbedtls_md_hmac(info, key->bytes, sizeof(key->bytes), message, length, tag) != 0) {
        memset(tag, 0, 32);
        return -1;
    }
    return 0;
}
