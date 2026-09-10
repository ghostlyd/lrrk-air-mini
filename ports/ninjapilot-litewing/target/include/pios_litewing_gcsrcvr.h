/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LITEWING_GCSRCVR_H
#define LITEWING_GCSRCVR_H
#include <stdint.h>
#include "uavobjectmanager.h"
int32_t PIOS_LiteWing_GCSReceiver_Unpack(UAVObjHandle obj, uint16_t instance,
                                       const uint8_t *data, int64_t received_us);
/* Trusted controller APIs, not wire endpoints. Caller must validate the session
 * handshake and serialize its current disarmed observation with ownership work.
 * Returns 0/-1. Claim cannot preempt fresh USB input. Release requires the same
 * session and disarmed==1; link loss alone must not transfer control to USB.
 * These calls reserve/exclude input only, never arm or publish motor commands. */
int32_t PIOS_LiteWing_GCSReceiver_ClaimWireless(const uint8_t session[16], int disarmed);
int32_t PIOS_LiteWing_GCSReceiver_ReleaseWireless(const uint8_t session[16], int disarmed);
#endif
