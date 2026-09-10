#pragma once
#include <stddef.h>
typedef struct { int marker; } mbedtls_md_info_t;
enum { MBEDTLS_MD_SHA256=6 };
const mbedtls_md_info_t *mbedtls_md_info_from_type(int);
int mbedtls_md_hmac(const mbedtls_md_info_t *, const unsigned char *, size_t,
                    const unsigned char *, size_t, unsigned char *);
