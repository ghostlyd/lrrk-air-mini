#include "pios_litewing_pilot_mac.h"
#include "pilot_mac_sdk.h"
#include <assert.h>
#include <string.h>

static int lookup_fail, hmac_fail, calls;
static const mbedtls_md_info_t info = {1};
const mbedtls_md_info_t *mbedtls_md_info_from_type(int kind) {
    assert(kind==MBEDTLS_MD_SHA256);
    return lookup_fail ? NULL : &info;
}
int mbedtls_md_hmac(const mbedtls_md_info_t *md, const unsigned char *key,
                    size_t key_size, const unsigned char *message,
                    size_t size, unsigned char *tag) {
    assert(md==&info && key_size==32 && key[0]==0x45);
    assert(size==3 && !memcmp(message,"abc",3));
    calls++;
    memset(tag, 0x72, 32);
    return hmac_fail ? -1 : 0;
}
static void zero(const unsigned char tag[32]) {
    for(int i=0;i<32;i++) assert(tag[i]==0);
}
int main(void) {
    struct lw_pilot_mac_key key = {{0x45}};
    unsigned char tag[32];
    memset(tag,0xa5,32);
    assert(lw_pilot_mac(NULL,(const unsigned char *)"abc",3,tag)==-1); zero(tag);
    memset(tag,0xa5,32);
    assert(lw_pilot_mac(&key,NULL,3,tag)==-1); zero(tag);
    assert(lw_pilot_mac(&key,(const unsigned char *)"abc",3,NULL)==-1);
    assert(calls==0);
    lookup_fail=1;
    memset(tag,0xa5,32);
    assert(lw_pilot_mac(&key,(const unsigned char *)"abc",3,tag)==-1); zero(tag);
    assert(calls==0);
    lookup_fail=0; hmac_fail=1;
    assert(lw_pilot_mac(&key,(const unsigned char *)"abc",3,tag)==-1); zero(tag);
    assert(calls==1);
    hmac_fail=0;
    assert(lw_pilot_mac(&key,(const unsigned char *)"abc",3,tag)==0);
    assert(calls==2);
    for(int i=0;i<32;i++) assert(tag[i]==0x72);
    return 0;
}
