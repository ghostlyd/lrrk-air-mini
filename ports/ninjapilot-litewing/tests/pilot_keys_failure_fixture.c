/* Inject SDK failures only; successful derivation still uses real mbedTLS. */
#include "mbedtls/hkdf.h"
#include <string.h>
static int failure_call, calls;
void lw_test_fail_at(int call) { failure_call = call; calls = 0; }
int lw_test_rfc5869(unsigned char out[42])
{
    unsigned char ikm[22], salt[13], info[10];
    memset(ikm, 0x0b, sizeof(ikm));
    for (unsigned i = 0; i < sizeof(salt); ++i) salt[i] = (unsigned char)i;
    for (unsigned i = 0; i < sizeof(info); ++i) info[i] = (unsigned char)(0xf0 + i);
    return mbedtls_hkdf(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),
                        salt, sizeof(salt), ikm, sizeof(ikm),
                        info, sizeof(info), out, 42);
}
static int checked_hkdf(const mbedtls_md_info_t *md,
    const unsigned char *salt, size_t salt_len,
    const unsigned char *ikm, size_t ikm_len,
    const unsigned char *info, size_t info_len,
    unsigned char *okm, size_t okm_len)
{
    if (++calls == failure_call) {
        memset(okm, 0xa5, okm_len);
        return -1;
    }
    return mbedtls_hkdf(md, salt, salt_len, ikm, ikm_len,
                        info, info_len, okm, okm_len);
}
#define mbedtls_hkdf checked_hkdf
#include "../target/pios_litewing_pilot_keys.c"
