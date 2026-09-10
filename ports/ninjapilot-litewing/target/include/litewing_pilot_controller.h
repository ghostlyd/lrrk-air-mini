/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "litewing_pilot_session.h"

/* Trusted transport controller, never a model/tool API. A single owning task
 * or mutex MUST serialize every call, including observations and send failure.
 * disarmed/neutral are current validated flight/settings observations, not wire
 * fields. The platform adapter must supply them; this module does not invent
 * channel mapping. now_us is receive-completion time before queue/lock delay.
 * The controller uses current platform time for session monotonicity/expiry;
 * an earlier queued receive time never replaces the challenge age origin.
 * PublishWireless independently checks current platform time at commit.
 * Buffers/state must not overlap. Initialize once before receiver ownership.
 */
struct lw_pilot_controller {
    struct lw_pilot_session session;
    uint8_t owner[16]; /* Kept after retirement to invalidate/release reservation. */
    int owned;
};
void lw_controller_init(struct lw_pilot_controller *controller);
enum lw_session_result lw_controller_receive(struct lw_pilot_controller *controller,
    const uint8_t *wire, size_t size, const uint8_t root[32], int64_t now_us,
    int disarmed, int neutral, lw_session_rng random, void *random_ctx,
    uint8_t *reply, size_t capacity, size_t *written);
/* Call periodically even without packets. Fault on socket/AP/task failure or
 * failed send. Neither operation releases ownership or writes PWM. */
int lw_controller_tick(struct lw_pilot_controller *controller, int64_t now_us);
void lw_controller_fault(struct lw_pilot_controller *controller);
/* Explicit local recovery only, with fresh disarmed AND neutral observations. */
int lw_controller_release(struct lw_pilot_controller *controller,
    int disarmed, int neutral);
