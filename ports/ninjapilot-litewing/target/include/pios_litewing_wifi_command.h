/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#ifndef LW_WIFI_COMMAND_PORT
#define LW_WIFI_COMMAND_PORT 2390
#endif

/* Trusted boot caller only, after checked board/receiver/settings readiness.
 * Called by checked System startup. Returns 0 for task creation, NOT AP/link
 * readiness. Creation failure starts no AP and permits retry unless maintenance
 * stop has been requested. After successful
 * creation every further launch is refused until reboot, including after exit.
 * The task alone owns AP, root, controller and socket. No caller receives keys.
 * Do not externally delete/suspend this task or concurrently operate Wi-Fi/AP.
 * STOP/expiry/failure never releases wireless ownership; v1 recovery is reboot.
 * This command-only boundary exports no telemetry. Port override must be 1..65535.
 */
int lw_wifi_command_start(void);
/* Trusted maintenance caller only. Nonblocking and idempotent; permanently
 * inhibits future starts until reboot, including races with task creation.
 * This is not an immediate motor-stop API or a Disarmed/ownership check.
 * The caller must obtain maintenance exclusion and enforce its own bounded
 * wait before performing credential writes. Never force-delete the task. */
void lw_wifi_command_request_stop(void);
/* Acquire query: true only after no launch can acquire resources and all
 * task-owned socket/AP resources, admission cleanup and local secret-buffer
 * work have finished. Retained wireless ownership is NOT released. Cleanup
 * failures can keep this false indefinitely. Task self-deletion may follow
 * publication, so true does not prove RTOS stack reclamation. No resource or
 * credential work is performed by the task after publishing true. */
int lw_wifi_command_is_quiescent(void);
