/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#ifndef LW_WIFI_COMMAND_PORT
#define LW_WIFI_COMMAND_PORT 2390
#endif

/* Trusted boot caller only, after checked board/receiver/settings readiness.
 * No startup hook calls this yet. Returns 0 for task creation, NOT AP/link
 * readiness. Creation failure starts no AP and permits retry. After successful
 * creation every further launch is refused until reboot, including after exit.
 * The task alone owns AP, root, controller and socket. No caller receives keys.
 * Do not externally delete/suspend this task or concurrently operate Wi-Fi/AP.
 * STOP/expiry/failure never releases wireless ownership; v1 recovery is reboot.
 * This command-only boundary exports no telemetry. Port override must be 1..65535.
 */
int lw_wifi_command_start(void);
