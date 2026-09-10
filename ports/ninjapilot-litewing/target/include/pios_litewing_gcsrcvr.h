/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LITEWING_GCSRCVR_H
#define LITEWING_GCSRCVR_H
#include <stdint.h>
#include "uavobjectmanager.h"
int32_t PIOS_LiteWing_GCSReceiver_Unpack(UAVObjHandle obj, uint16_t instance,
                                       const uint8_t *data, int64_t received_us);
/* Trusted serialized admission transaction only, after authenticating HELLO.
 * Blocks UART writes, not read requests; does not grant pilot ownership/input.
 * Refuses fresh USB input or in-flight writes. Caller must end on every path,
 * including timeout/fault; no wait/network receive while holding this guard.
 * Token prevents an old cleanup from releasing a newer transaction. It does
 * not exclude local UAVObject setters: caller must separately control those. */
int32_t PIOS_LiteWing_GCSReceiver_BeginAdmission(int disarmed, uint64_t *token);
int32_t PIOS_LiteWing_GCSReceiver_EndAdmission(uint64_t token);
/* Execute a trusted persistence load outside the spinlock, but counted as an
 * in-flight writer until synchronous load/callback work finishes. Asynchronous
 * callbacks are not covered. Refuse during admission/ownership.
 * Permits boot-time loading before receiver initialization. Not a wire API. */
int32_t PIOS_LiteWing_GCSReceiver_SettingsLoad(UAVObjHandle obj, uint16_t instance,
    int32_t (*load)(UAVObjHandle, uint16_t));
/* Trusted controller APIs, not wire endpoints. Caller must validate the session
 * handshake and serialize its current disarmed observation with ownership work.
 * Returns 0/-1. Claim cannot preempt fresh USB input. Release requires the same
 * session and disarmed==1; link loss alone must not transfer control to USB.
 * These calls reserve/exclude input only, never arm or publish motor commands. */
int32_t PIOS_LiteWing_GCSReceiver_ClaimWireless(const uint8_t session[16], int disarmed);
int32_t PIOS_LiteWing_GCSReceiver_ReleaseWireless(const uint8_t session[16], int disarmed);
struct lw_pilot_session;
/* Trusted controller holds its session mutex across prepare and this call.
 * owner is the separately retained identity from reservation (survives STOP).
 * Commit and receiver publication share receiver_lock; no crypto or object
 * manager calls occur under that lock. Returns 0 only for published input.
 * After STOP/retirement call this to invalidate input without releasing ownership.
 * Inputs must not overlap session storage. No model or wire endpoint calls it. */
int32_t PIOS_LiteWing_GCSReceiver_PublishWireless(const uint8_t owner[16],
                                                struct lw_pilot_session *session);
#endif
