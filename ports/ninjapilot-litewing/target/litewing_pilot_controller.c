/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "litewing_pilot_controller.h"
#include "pios.h"
#include <freertos/FreeRTOS.h>
#include <esp_timer.h>
#include "pios_litewing_gcsrcvr.h"
#include "litewing_pilot_wire.h"
#include "pios_litewing_pilot_mac.h"
#include <mbedtls/platform_util.h>
#include <string.h>

void lw_controller_init(struct lw_pilot_controller *c,
    const struct lw_pilot_channel mapping[5])
{
    if (!c) return;
    memset(c, 0, sizeof(*c));
    lw_session_init(&c->session);
    if (mapping) memcpy(c->mapping, mapping, sizeof(c->mapping));
}

static int neutral_claim(struct lw_pilot_controller *c, const uint8_t *wire, size_t size)
{
    struct lw_wire_frame frame = {0};
    struct lw_pilot_mac_key key;
    uint16_t channels[8] = {0};
    memcpy(key.bytes, c->session.keys.c2b, sizeof(key.bytes));
    int accepted = 0;
    if (lw_wire_decode(wire, size, 0, lw_pilot_mac, &key, &frame) == 0 &&
        frame.kind == 3 && frame.payload_len == 16) {
        for (unsigned i=0; i<8; ++i)
            channels[i] = ((uint16_t)frame.payload[2*i] << 8) | frame.payload[2*i+1];
        accepted = lw_pilot_neutral(c->mapping, channels);
    }
    mbedtls_platform_zeroize(&key, sizeof(key));
    mbedtls_platform_zeroize(&frame, sizeof(frame));
    return accepted;
}

void lw_controller_fault(struct lw_pilot_controller *c)
{
    if (!c) return;
    lw_session_retire(&c->session);
    if (c->owned)
        (void)PIOS_LiteWing_GCSReceiver_PublishWireless(c->owner, &c->session);
    if (c->admission_guard &&
        PIOS_LiteWing_GCSReceiver_EndAdmission(c->admission_guard)==0)
        c->admission_guard=0;
}

int lw_controller_tick(struct lw_pilot_controller *c, int64_t now_us)
{
    if (!c) return -1;
    if (c->admission_guard) {
        lw_controller_fault(c);
        return -1;
    }
    if (lw_session_tick(&c->session, now_us) < 0) {
        lw_controller_fault(c);
        return -1;
    }
    return 0;
}

int lw_controller_release(struct lw_pilot_controller *c, int disarmed, int neutral)
{
    if (!c || !c->owned || disarmed != 1 || neutral != 1) return -1;
    lw_controller_fault(c);
    if (PIOS_LiteWing_GCSReceiver_ReleaseWireless(c->owner, disarmed) != 0)
        return -1;
    memset(c->owner, 0, sizeof(c->owner));
    c->owned = 0;
    return 0;
}

enum lw_session_result lw_controller_challenge(struct lw_pilot_controller *c,
    const uint8_t root[32], lw_session_rng random, void *random_ctx,
    uint8_t *reply, size_t capacity, size_t *written)
{
    if (written) *written = 0;
    if (!c || !written) return LW_REJECT;
    enum lw_session_result r = lw_session_issue_challenge(&c->session, root,
        esp_timer_get_time(), random, random_ctx, reply, capacity, written);
    if (r == LW_RETIRED || c->session.phase == LW_CLOSED)
        lw_controller_fault(c);
    return r;
}

enum lw_session_result lw_controller_receive_observed(struct lw_pilot_controller *c,
    const uint8_t *wire, size_t size, const uint8_t root[32], int64_t received_us,
    lw_pilot_mapping_reader read_mapping, lw_session_rng random, void *random_ctx,
    uint8_t *reply, size_t capacity, size_t *written)
{
    if (written) *written=0;
    if (!c || !written) return LW_REJECT;
    if (lw_controller_tick(c,esp_timer_get_time())<0) return LW_RETIRED;
    if (c->owned)
        return lw_controller_receive(c,wire,size,root,received_us,0,0,random,
            random_ctx,reply,capacity,written);
    if (!read_mapping || (c->session.phase==LW_CLOSED && !root)) return LW_REJECT;
    struct lw_wire_frame frame={0};
    struct lw_pilot_mac_key key;
    const int pending=c->session.phase==LW_PENDING;
    memcpy(key.bytes,pending ? c->session.keys.c2b : root,sizeof(key.bytes));
    int authenticated=lw_wire_decode(wire,size,0,lw_pilot_mac,&key,&frame)==0 &&
        frame.kind==(pending ? 3 : 1) && frame.payload_len==(pending ? 16 : 32);
    mbedtls_platform_zeroize(&key,sizeof(key));
    mbedtls_platform_zeroize(&frame,sizeof(frame));
    if (!authenticated) return LW_REJECT;
    struct lw_pilot_channel mapping[5]={0};
    if (read_mapping(mapping)!=0 ||
        PIOS_LiteWing_GCSReceiver_BeginAdmission(1,&c->admission_guard)!=0) {
        lw_controller_fault(c);
        return LW_RETIRED;
    }
    enum lw_session_result result=LW_RETIRED;
    if (read_mapping(mapping)==0) {
        memcpy(c->mapping,mapping,sizeof(mapping));
        result=lw_controller_receive(c,wire,size,root,received_us,1,1,random,
            random_ctx,reply,capacity,written);
    } else lw_controller_fault(c);
    if (c->admission_guard) {
        if (PIOS_LiteWing_GCSReceiver_EndAdmission(c->admission_guard)==0)
            c->admission_guard=0;
        else {
            if (reply && *written) memset(reply,0,*written);
            *written=0;
            lw_controller_fault(c);
            result=LW_RETIRED;
        }
    }
    return result;
}

enum lw_session_result lw_controller_receive(struct lw_pilot_controller *c,
    const uint8_t *wire, size_t size, const uint8_t root[32], int64_t now_us,
    int disarmed, int neutral, lw_session_rng random, void *random_ctx,
    uint8_t *reply, size_t capacity, size_t *written)
{
    if (written) *written = 0;
    if (!c || !written) return LW_REJECT;
    const int64_t processing_us = esp_timer_get_time();
    if (now_us < 0 || now_us > processing_us) {
        lw_controller_fault(c);
        return LW_RETIRED;
    }
    /* Session time is the processing clock, shared with receiver commit/tick.
     * A queued packet's earlier receive time is not a clock rollback. Freshness
     * remains measured from its authenticated challenge, never from either read
     * time; processing delay can only shorten the acceptance window. */
    now_us = processing_us;
    if (c->owned) {
        enum lw_session_result r = lw_session_prepare_control(&c->session, wire, size, now_us);
        if (r == LW_PILOT_CANDIDATE) {
            if (PIOS_LiteWing_GCSReceiver_PublishWireless(c->owner, &c->session) == 0)
                return r;
            lw_controller_fault(c);
            return LW_RETIRED;
        }
        if (r == LW_RETIRED || c->session.phase == LW_CLOSED)
            lw_controller_fault(c);
        return r;
    }
    if (disarmed != 1 || neutral != 1) {
        lw_controller_fault(c);
        return LW_RETIRED;
    }
    if (c->session.phase == LW_PENDING && !neutral_claim(c, wire, size)) {
        /* Invalid traffic cannot skip ordinary expiry processing. */
        return lw_controller_tick(c, now_us) < 0 ? LW_RETIRED : LW_REJECT;
    }
    enum lw_session_result r = lw_session_receive(&c->session, wire, size, root,
        now_us, disarmed == 1 && neutral == 1, 1, random, random_ctx,
        reply, capacity, written);
    if (r == LW_HANDSHAKE_REPLY && c->session.phase == LW_ACTIVE) {
        if (PIOS_LiteWing_GCSReceiver_ClaimWireless(c->session.session, disarmed) != 0) {
            /* ACCEPT may have been encoded but must never leave this boundary. */
            memset(reply, 0, *written);
            *written = 0;
            lw_controller_fault(c);
            return LW_RETIRED;
        }
        memcpy(c->owner, c->session.session, sizeof(c->owner));
        c->owned = 1;
    }
    return r;
}
