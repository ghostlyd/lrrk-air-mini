/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "litewing_pilot_neutral.h"
/* Read current RAM settings loaded from persistence; never write defaults.
 * Returns 0 only for observed Disarmed and supported GCS-only primary mapping.
 * Output clears on failure. Caller must exclude settings writers across this
 * read, controller initialization and ownership admission, and recheck current
 * disarmed state at CLAIM. This read is not a lock or a freshness guarantee.
 * Optional collective/accessory inputs are unsupported by this pilot profile.
 */
int PIOS_LiteWing_PilotReadAdmissionMapping(struct lw_pilot_channel out[5]);
