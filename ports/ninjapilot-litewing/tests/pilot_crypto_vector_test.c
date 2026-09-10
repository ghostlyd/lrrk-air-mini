/* Real mbedTLS KAT plus a frozen synthetic LWPL vector. No live credentials. */
#include "pios_litewing_pilot_mac.h"
#include "litewing_pilot_wire.h"
#include "mbedtls/md.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void from_hex(const char *hex, unsigned char *out, size_t size)
{
    assert(strlen(hex)==size*2);
    for(size_t i=0;i<size;i++) {
        unsigned value;
        assert(sscanf(hex+2*i,"%2x",&value)==1);
        out[i]=(unsigned char)value;
    }
}

int main(void)
{
    /* RFC 4231 section 4.2 uses a 20-byte key, unlike our adapter's 32 bytes. */
    unsigned char rfc_key[20], expected[32], actual[32];
    memset(rfc_key,0x0b,sizeof(rfc_key));
    from_hex("b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7",expected,32);
    const mbedtls_md_info_t *md=mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    assert(md);
    assert(mbedtls_md_hmac(md,rfc_key,20,(const unsigned char *)"Hi There",8,actual)==0);
    assert(!memcmp(actual,expected,32));

    const char *frozen=
        "4c57504c01000500737373737373737373737373737373730000000000000009"
        "6363636363636363636363636363636300026162"
        "d30dfa9f0d0637cdf7dfc393c62f8630e567f3cf62fd5382741c7e236a76e70e";
    unsigned char vector[84], wire[84];
    from_hex(frozen,vector,sizeof(vector));
    struct lw_pilot_mac_key key;
    memset(key.bytes,'k',32);
    struct lw_wire_frame frame={.direction=0,.kind=5,.sequence=9,.payload_len=2};
    memset(frame.session,'s',16); memset(frame.challenge,'c',16);
    memcpy(frame.payload,"ab",2);
    size_t written=0;
    assert(lw_wire_encode(&frame,lw_pilot_mac,&key,wire,sizeof(wire),&written)==0);
    assert(written==84 && !memcmp(wire,vector,84));
    struct lw_wire_frame decoded;
    assert(lw_wire_decode(vector,84,0,lw_pilot_mac,&key,&decoded)==0);
    assert(decoded.sequence==9 && decoded.payload_len==2 && !memcmp(decoded.payload,"ab",2));
    for(size_t i=0;i<84;i++) {
        vector[i]^=1;
        assert(lw_wire_decode(vector,84,0,lw_pilot_mac,&key,&decoded)==-1);
        vector[i]^=1;
    }
    return 0;
}
