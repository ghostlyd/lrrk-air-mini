/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "litewing_pilot_session.h"
#include "litewing_pilot_neutral.h"

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
    struct lw_pilot_channel mapping[5];
    uint64_t admission_guard; /* Retained if clock failure prevents cleanup. */
};
/* mapping is a validated persisted-settings snapshot; NULL disables admission.
 * Caller must prevent settings changes during admission/ownership, or fault the
 * controller and rebuild this snapshot before another admission. */
void lw_controller_init(struct lw_pilot_controller *controller,
    const struct lw_pilot_channel mapping[5]);
enum lw_session_result lw_controller_receive(struct lw_pilot_controller *controller,
    const uint8_t *wire, size_t size, const uint8_t root[32], int64_t now_us,
    int disarmed, int neutral, lw_session_rng random, void *random_ctx,
    uint8_t *reply, size_t capacity, size_t *written);
/* Platform entry: read_mapping must return 0 only for current Disarmed and a
 * validated mapping (PIOS_LiteWing_PilotReadAdmissionMapping satisfies this).
 * Admission authenticates before reads, then re-reads inside the UART guard.
 * Still requires one serialized owning task and no concurrent local setters. */
typedef int (*lw_pilot_mapping_reader)(struct lw_pilot_channel out[5]);
enum lw_session_result lw_controller_receive_observed(struct lw_pilot_controller *c,
    const uint8_t *wire, size_t size, const uint8_t root[32], int64_t received_us,
    lw_pilot_mapping_reader read_mapping, lw_session_rng random, void *random_ctx,
    uint8_t *reply, size_t capacity, size_t *written);
/* Call periodically even without packets. Fault on socket/AP/task failure or
 * failed send. Neither operation releases ownership or writes PWM. */
int lw_controller_tick(struct lw_pilot_controller *controller, int64_t now_us);
/* Owning task calls this periodically; 20ms issuance limit is enforced by core.
 * Never send non-reply output. Send failure must call controller_fault. */
enum lw_session_result lw_controller_challenge(struct lw_pilot_controller *controller,
    const uint8_t root[32], lw_session_rng random, void *random_ctx,
    uint8_t *reply, size_t capacity, size_t *written);
void lw_controller_fault(struct lw_pilot_controller *controller);
/* Explicit local recovery only, with fresh disarmed AND neutral observations. */
int lw_controller_release(struct lw_pilot_controller *controller,
    int disarmed, int neutral);
