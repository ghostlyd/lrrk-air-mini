/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdint.h>

/* Snapshot of persisted primary GCS mappings, ordered throttle/roll/pitch/yaw/
 * flight-mode. Platform adapter must verify GCS groups and unsupported inputs
 * before constructing this snapshot; channel numbers are one-based. */
struct lw_pilot_channel {
    uint8_t channel;
    int16_t minimum, neutral, maximum;
};
/* Strict admission check: throttle at calibrated minimum, centered axes and
 * flight-mode at calibrated neutral. No guessed deadband or default mapping.
 * All eight wire channels must be in protocol range. Samples must already be
 * authenticated and fresh; this predicate grants neither ownership nor arming. */
int lw_pilot_neutral(const struct lw_pilot_channel mapping[5],
    const uint16_t channels[8]);
