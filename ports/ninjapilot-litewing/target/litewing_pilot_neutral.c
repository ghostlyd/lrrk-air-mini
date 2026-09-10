/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "litewing_pilot_neutral.h"

int lw_pilot_neutral(const struct lw_pilot_channel mapping[5],
    const uint16_t channels[8])
{
    if (!mapping || !channels) return 0;
    for (unsigned i=0; i<8; ++i)
        if (channels[i]<1000 || channels[i]>2000) return 0;
    unsigned used=0;
    for (unsigned i=0; i<5; ++i) {
        const struct lw_pilot_channel *m=&mapping[i];
        if (m->channel<1 || m->channel>8 || m->minimum<1000 ||
            m->minimum>2000 || m->maximum<1000 || m->maximum>2000 ||
            m->minimum==m->maximum) return 0;
        int lo=m->minimum<m->maximum ? m->minimum : m->maximum;
        int hi=m->minimum>m->maximum ? m->minimum : m->maximum;
        if (m->neutral<lo || m->neutral>hi) return 0;
        unsigned bit=1u<<(m->channel-1);
        if (used & bit) return 0;
        used |= bit;
        uint16_t expected=(uint16_t)(i==0 ? m->minimum : m->neutral);
        if (channels[m->channel-1]!=expected) return 0;
    }
    return 1;
}
