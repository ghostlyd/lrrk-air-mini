/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "litewing_pilot_controller.h"
#include "pios.h"
#include <freertos/FreeRTOS.h>
#include <esp_timer.h>
#include "pios_litewing_gcsrcvr.h"
#include <string.h>

void lw_controller_init(struct lw_pilot_controller *c)
{
    if (!c) return;
    memset(c, 0, sizeof(*c));
    lw_session_init(&c->session);
}

void lw_controller_fault(struct lw_pilot_controller *c)
{
    if (!c) return;
    lw_session_retire(&c->session);
    if (c->owned)
        (void)PIOS_LiteWing_GCSReceiver_PublishWireless(c->owner, &c->session);
}

int lw_controller_tick(struct lw_pilot_controller *c, int64_t now_us)
{
    if (!c) return -1;
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
