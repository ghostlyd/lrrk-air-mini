#include "litewing_wifi_config.h"
#include <assert.h>
#include <string.h>

static void empty(const struct lw_wifi_config *c) {
    const unsigned char *p=(const unsigned char *)c;
    for(size_t i=0;i<sizeof(*c);++i) assert(p[i]==0);
}
int main(void) {
    uint8_t b[136]={ 'L','W','C','F',1,4,16,0 };
    memset(b+8,0x42,32); memcpy(b+40,"test",4);
    memcpy(b+72,"fixture-key-1234",16);
    struct lw_wifi_config c;
    assert(lw_wifi_config_decode(b,sizeof(b),&c)==0);
    assert(!strcmp(c.ssid,"test") && !strcmp(c.password,"fixture-key-1234"));
    for(size_t i=0;i<32;++i) assert(c.root[i]==0x42);
    lw_wifi_config_clear(&c); empty(&c);
    for(size_t i=0;i<sizeof(b);++i) {
        memset(&c,0xaa,sizeof(c));
        assert(lw_wifi_config_decode(b,i,&c)!=0); empty(&c);
    }
    const size_t offsets[]={0,4,5,6,7,44,88};
    const uint8_t values[]={0,2,33,64,1,1,1};
    for(size_t i=0;i<sizeof(offsets)/sizeof(*offsets);++i) {
        uint8_t saved=b[offsets[i]]; b[offsets[i]]=values[i];
        memset(&c,0xaa,sizeof(c));
        assert(lw_wifi_config_decode(b,sizeof(b),&c)!=0); empty(&c);
        b[offsets[i]]=saved;
    }
    b[6]=15; assert(lw_wifi_config_decode(b,sizeof(b),&c)!=0); empty(&c); b[6]=16;
    b[5]=0; assert(lw_wifi_config_decode(b,sizeof(b),&c)!=0); empty(&c); b[5]=4;
    b[40]=0; assert(lw_wifi_config_decode(b,sizeof(b),&c)!=0); empty(&c); b[40]='t';
    b[72]=127; assert(lw_wifi_config_decode(b,sizeof(b),&c)!=0); empty(&c); b[72]='f';
    memset(b+8,0,32); assert(lw_wifi_config_decode(b,sizeof(b),&c)!=0); empty(&c);
    assert(lw_wifi_config_decode(NULL,136,&c)!=0); empty(&c);
    assert(lw_wifi_config_decode(b,136,NULL)!=0);
    lw_wifi_config_clear(NULL);
    memset(b+8,0x42,32); b[5]=32; b[6]=63;
    memset(b+40,'s',32); memset(b+72,'p',63);
    assert(lw_wifi_config_decode(b,136,&c)==0);
    assert(strlen(c.ssid)==32 && strlen(c.password)==63);
    return 0;
}
