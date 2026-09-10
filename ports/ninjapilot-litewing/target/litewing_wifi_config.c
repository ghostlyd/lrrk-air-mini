/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "litewing_wifi_config.h"
#include <string.h>

void lw_wifi_config_clear(struct lw_wifi_config *config)
{
    if (!config) return;
    volatile unsigned char *p=(volatile unsigned char *)config;
    for (size_t i=0;i<sizeof(*config);++i) p[i]=0;
}

static int text_field(const uint8_t *field, size_t used, size_t capacity)
{
    for (size_t i=0;i<capacity;++i) {
        if (i<used) {
            if (field[i]<32 || field[i]>126) return -1;
        } else if (field[i]) return -1;
    }
    return 0;
}

int lw_wifi_config_decode(const uint8_t *blob, size_t size, struct lw_wifi_config *out)
{
    if (!out) return -1;
    lw_wifi_config_clear(out);
    if (!blob || size!=LW_WIFI_CONFIG_SIZE || memcmp(blob,"LWCF",4) ||
        blob[4]!=1 || blob[5]<1 || blob[5]>32 || blob[6]<16 || blob[6]>63 || blob[7])
        return -1;
    unsigned nonzero=0;
    for (size_t i=8;i<40;++i) nonzero|=blob[i];
    if (!nonzero || text_field(blob+40,blob[5],32) ||
        text_field(blob+72,blob[6],64)) return -1;
    memcpy(out->root,blob+8,32);
    memcpy(out->ssid,blob+40,blob[5]);
    memcpy(out->password,blob+72,blob[6]);
    return 0;
}
