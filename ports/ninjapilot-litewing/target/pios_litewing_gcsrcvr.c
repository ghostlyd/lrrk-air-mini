/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 LRRK contributors
 *
 * LiteWing's single GCS receiver uses the ESP32 monotonic clock, not RTC
 * callbacks. Only a successful received UAVObject packet supplies input.
 * Local setters, delayed event callbacks and telemetry/logging events cannot
 * renew it. Expiry is enforced on every consumer read; no timer task is needed.
 * This is input-age enforcement, not a bound on physical motor-cut latency.
 */
#include "pios.h"
#include <string.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include "uavobjectmanager.h"
#include "pios_gcsrcvr_priv.h"
#include "pios_litewing_gcsrcvr.h"
#include "litewing_pilot_session.h"

#define LITEWING_GCS_ID UINT32_C(0x4c474353)
#define LITEWING_GCS_TIMEOUT_US INT64_C(100000)

_Static_assert(GCSRECEIVER_CHANNEL_NUMELEM == 8, "review changed receiver layout");
_Static_assert(sizeof(GCSReceiverData) == 16, "review changed receiver layout");

static portMUX_TYPE receiver_lock = portMUX_INITIALIZER_UNLOCKED;
static GCSReceiverData receiver_data;
static int64_t received_us;
static bool initialized;
static bool have_timestamp;
static bool valid;
static bool wireless_owner;
static uint8_t owner_session[16];
static uint64_t owner_generation;
static int64_t usb_fence_us = -1;
static uint32_t usb_inflight;

int32_t PIOS_LiteWing_GCSReceiver_ClaimWireless(const uint8_t session[16], int disarmed)
{
    if (!session || disarmed != 1) return -1;
    int32_t result = -1;
    portENTER_CRITICAL(&receiver_lock);
    const int64_t now = esp_timer_get_time();
    if (initialized && !wireless_owner && usb_inflight == 0 && now >= 0 &&
        now >= usb_fence_us && owner_generation != UINT64_MAX &&
        (!have_timestamp || now >= received_us)) {
        if (valid && now - received_us >= LITEWING_GCS_TIMEOUT_US) valid = false;
        if (!valid) {
            memcpy(owner_session, session, sizeof(owner_session));
            wireless_owner = true;
            ++owner_generation;
            usb_fence_us = now;
            result = 0;
        }
    }
    portEXIT_CRITICAL(&receiver_lock);
    return result;
}

int32_t PIOS_LiteWing_GCSReceiver_ReleaseWireless(const uint8_t session[16], int disarmed)
{
    if (!session || disarmed != 1) return -1;
    int32_t result = -1;
    portENTER_CRITICAL(&receiver_lock);
    const int64_t now = esp_timer_get_time();
    if (initialized && wireless_owner && !memcmp(session, owner_session, 16) &&
        now >= usb_fence_us && owner_generation != UINT64_MAX) {
        valid = false;
        wireless_owner = false;
        memset(owner_session, 0, sizeof(owner_session));
        ++owner_generation;
        usb_fence_us = now;
        result = 0;
    }
    portEXIT_CRITICAL(&receiver_lock);
    return result;
}

int32_t PIOS_LiteWing_GCSReceiver_PublishWireless(const uint8_t owner[16],
                                                struct lw_pilot_session *session)
{
    if (!session) return -1;
    struct lw_pilot_candidate candidate = {0};
    int32_t result = -1;
    portENTER_CRITICAL(&receiver_lock);
    const bool named_owner = initialized && wireless_owner && owner &&
                             !memcmp(owner, owner_session, 16);
    const bool state_owner = initialized && wireless_owner &&
                             !memcmp(session->session, owner_session, 16);
    if (!named_owner || !state_owner || session->phase != LW_ACTIVE) {
        if (named_owner || state_owner) valid = false;
        lw_session_retire(session);
    } else {
        const enum lw_session_result rc = lw_session_commit_control(
            session, esp_timer_get_time(), 1, &candidate);
        if (rc == LW_PILOT_CANDIDATE) {
            memcpy(receiver_data.Channel, candidate.channels, sizeof(candidate.channels));
            received_us = candidate.origin_us;
            have_timestamp = true;
            valid = true;
            result = 0;
        } else if (rc == LW_RETIRED) valid = false;
    }
    portEXIT_CRITICAL(&receiver_lock);
    return result;
}

/* The target-adapted parser supplies its immutable completion timestamp,
 * before receiveObject can wait on connection or object-manager locks. */
int32_t PIOS_LiteWing_GCSReceiver_Unpack(UAVObjHandle obj, uint16_t instance,
                                       const uint8_t *data, int64_t received_time)
{
    const bool receiver_packet = obj != NULL && obj == GCSReceiverHandle() &&
                                 instance == 0 && data != NULL;
    if (!receiver_packet) {
        return UAVObjUnpack(obj, instance, data);
    }

    /* Retain the timestamp from packet completion. Copy this packet, not
     * whatever a delayed event callback happens to find in shared storage.
     * UAVTalk validates the complete object length/CRC before this API call. */
    const int64_t arrival_us = received_time;
    portENTER_CRITICAL(&receiver_lock);
    const uint64_t generation = owner_generation;
    const bool permitted = !wireless_owner && arrival_us > usb_fence_us &&
                           usb_inflight != UINT32_MAX;
    /* Reservation refuses while storage/events may still be in flight. Never
     * hold the spinlock across the potentially blocking object-manager call. */
    if (permitted) ++usb_inflight;
    portEXIT_CRITICAL(&receiver_lock);
    if (!permitted) return -1;
    GCSReceiverData packet;
    memcpy(&packet, data, sizeof(packet));
    const int32_t result = UAVObjUnpack(obj, instance, data);
    portENTER_CRITICAL(&receiver_lock);
    --usb_inflight;
    if (result == 0 && initialized && !wireless_owner && generation == owner_generation &&
        arrival_us > usb_fence_us && arrival_us >= 0 &&
        (!have_timestamp || arrival_us > received_us)) {
        /* Older (or equal-time) completions cannot replace a newer packet. */
        receiver_data = packet;
        received_us = arrival_us;
        have_timestamp = true;
        valid = true;
    }
    portEXIT_CRITICAL(&receiver_lock);
    return result;
}

int32_t PIOS_GCSRCVR_Init(uint32_t *receiver_id)
{
    if (receiver_id == NULL) {
        return -1;
    }
    *receiver_id = 0;
    if (GCSReceiverHandle() == NULL) {
        return -1;
    }
    portENTER_CRITICAL(&receiver_lock);
    if (initialized) {
        portEXIT_CRITICAL(&receiver_lock);
        return -1;
    }
    initialized = true;
    have_timestamp = false;
    valid = false;
    *receiver_id = LITEWING_GCS_ID;
    portEXIT_CRITICAL(&receiver_lock);
    return 0;
}

static int32_t receiver_read(uint32_t receiver_id, uint8_t channel)
{
    portENTER_CRITICAL(&receiver_lock);
    int32_t result = PIOS_RCVR_NODRIVER;
    if (initialized && receiver_id == LITEWING_GCS_ID) {
        if (channel >= GCSRECEIVER_CHANNEL_NUMELEM) {
            result = PIOS_RCVR_INVALID;
        } else {
            const int64_t now_us = esp_timer_get_time();
            if (valid && (now_us < received_us ||
                          now_us - received_us >= LITEWING_GCS_TIMEOUT_US)) {
                /* Do not resurrect expired input when a clock recovers. */
                valid = false;
            }
            result = valid ? receiver_data.Channel[channel] : PIOS_RCVR_TIMEOUT;
        }
    }
    portEXIT_CRITICAL(&receiver_lock);
    return result;
}

const struct pios_rcvr_driver pios_gcsrcvr_rcvr_driver = {
    .read = receiver_read,
};
