/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "pios_litewing_wifi_command.h"
#include "pios_litewing_wifi_ap.h"
#include "pios_litewing_pilot_mapping.h"
#include "litewing_pilot_controller.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_netif.h>
#include <esp_random.h>
#include <esp_timer.h>
#include <lwip/sockets.h>
#include <mbedtls/platform_util.h>
#include <errno.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <string.h>

_Static_assert(LW_WIFI_COMMAND_PORT > 0 && LW_WIFI_COMMAND_PORT <= 65535,
               "command UDP port must be 1..65535");
enum { WIRE_MAX = 594, READ_MAX = WIRE_MAX + 1, READS_PER_TURN = 4,
       TURN_US = 2000, SETUP_INTERVAL_US = 10000, READY_TIMEOUT_US = 2000000,
       STACK_BYTES = 8192 };
/* One atomic word serializes launch reservation with the permanent stop fence.
 * STOP and QUIESCENT only accumulate. RESERVED can return to zero solely when
 * creation fails and no stop won the race; successful launch keeps it forever.
 * No separate "running" publication can overwrite an early task completion. */
enum { COMMAND_RESERVED = 1u, COMMAND_STOP = 2u, COMMAND_QUIESCENT = 4u };
static atomic_uint lifecycle;

void lw_wifi_command_request_stop(void)
{
    unsigned previous = atomic_fetch_or_explicit(&lifecycle, COMMAND_STOP, memory_order_acq_rel);
    /* Winning before reservation inhibits every future launch. No task or
     * resource acquisition exists to await in this case. */
    if (!(previous & COMMAND_RESERVED))
        atomic_fetch_or_explicit(&lifecycle, COMMAND_QUIESCENT, memory_order_release);
}

int lw_wifi_command_is_quiescent(void)
{
    return (atomic_load_explicit(&lifecycle, memory_order_acquire) & COMMAND_QUIESCENT) != 0;
}

static bool stop_requested(void)
{
    return (atomic_load_explicit(&lifecycle, memory_order_acquire) & COMMAND_STOP) != 0;
}

struct command_state {
    struct lw_pilot_controller controller;
    uint8_t root[32], wire[READ_MAX], reply[WIRE_MAX];
    struct sockaddr_in peer;
    bool have_peer, healthy_ap;
    int64_t setup_refill_us;
    unsigned setup_tokens;
};

static TickType_t cleanup_delay(void)
{
    TickType_t ticks = pdMS_TO_TICKS(100);
    return ticks ? ticks : 1;
}

static int healthy_random(void *ctx, uint8_t *out, size_t size)
{
    struct command_state *s = ctx;
    if (!s->healthy_ap || stop_requested() || lw_wifi_ap_faults()) return -1;
    esp_fill_random(out, size);
    if (stop_requested() || lw_wifi_ap_faults()) {
        mbedtls_platform_zeroize(out, size);
        return -1;
    }
    return 0;
}

static bool unicast(uint32_t address)
{
    uint32_t host = ntohl(address);
    return host != 0 && host != UINT32_MAX && (host >> 24) != 0 &&
           (host >> 28) < 14;
}

static int ap_address(esp_netif_ip_info_t *info)
{
    if (stop_requested()) return -1;
    esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_AP_DEF");
    if (!netif || stop_requested()) return -1;
    int64_t started = esp_timer_get_time(), previous = started;
    if (started < 0) return -1;
    for (;;) {
        int64_t now = esp_timer_get_time();
        if (now < previous || now - started >= READY_TIMEOUT_US ||
            stop_requested() || lw_wifi_ap_faults()) return -1;
        previous = now;
        if (esp_netif_is_netif_up(netif)) {
            if (stop_requested() || esp_netif_get_ip_info(netif, info) != ESP_OK ||
                stop_requested()) return -1;
            uint32_t mask = ntohl(info->netmask.addr);
            uint32_t host = ntohl(info->ip.addr);
            uint32_t inverse = ~mask;
            /* Require a contiguous subnet with usable host addresses. */
            if (!unicast(info->ip.addr) || !mask || inverse < 3 ||
                (inverse & (inverse + 1)) || !(host & inverse) ||
                (host & inverse) == inverse) return -1;
            return 0;
        }
        if (stop_requested()) return -1;
        vTaskDelay(1);
    }
}

static bool valid_sender(const struct sockaddr_in *peer, socklen_t length,
                         const esp_netif_ip_info_t *local)
{
    uint32_t host = peer->sin_addr.s_addr & ~local->netmask.addr;
    return length == sizeof(*peer) && peer->sin_family == AF_INET && peer->sin_port &&
        unicast(peer->sin_addr.s_addr) &&
        (peer->sin_addr.s_addr & local->netmask.addr) == (local->ip.addr & local->netmask.addr) &&
        host && host != ~local->netmask.addr;
}

static bool same_peer(const struct sockaddr_in *a, const struct sockaddr_in *b)
{
    return a->sin_addr.s_addr == b->sin_addr.s_addr && a->sin_port == b->sin_port;
}

static int send_reply(struct command_state *s, int socket_fd, size_t written)
{
    if (!s->have_peer || !written || written > sizeof(s->reply) ||
        stop_requested() || lw_wifi_ap_faults()) return -1;
    /* Nonblocking: even EAGAIN or a short send loses this authenticated output
     * and is a transport fault, never an unbounded retry or silent drop. */
    return sendto(socket_fd, s->reply, written, 0, (struct sockaddr *)&s->peer,
                  sizeof(s->peer)) == (ssize_t)written ? 0 : -1;
}

static int service(struct command_state *s, int socket_fd)
{
    if (stop_requested() || lw_wifi_ap_faults()) return -1;
    struct lw_pilot_controller *c = &s->controller;
    int64_t now = esp_timer_get_time();
    bool admission_expired = c->session.phase == LW_PENDING && !c->owned &&
        !c->admission_guard && now >= c->session.last_us &&
        now - c->session.started_us >= 1000000;
    if (lw_controller_tick(c, now) < 0) {
        if (!admission_expired || c->owned || c->admission_guard) return -1;
        s->have_peer = false;
        mbedtls_platform_zeroize(&s->peer, sizeof(s->peer));
    }
    if (stop_requested() || (c->owned && c->session.phase == LW_CLOSED)) return -1;
    if (s->have_peer) {
        size_t written = 0;
        enum lw_session_result result = lw_controller_challenge(c, s->root,
            healthy_random, s, s->reply, sizeof(s->reply), &written);
        if (result == LW_RETIRED) return -1;
        if (result == LW_HANDSHAKE_REPLY && send_reply(s, socket_fd, written)) return -1;
    }
    return stop_requested() ? -1 : 0;
}

static void command_task(void *arg)
{
    (void)arg;
    struct command_state state = {.setup_refill_us = -1, .setup_tokens = 2};
    struct command_state *s = &state;
    lw_controller_init(&s->controller, NULL);
    int socket_fd = -1;
    bool ap_attempted = false;
    if (stop_requested()) goto end;
    ap_attempted = true;
    if (lw_wifi_ap_start(s->root) != 0 || stop_requested() || lw_wifi_ap_faults()) goto end;
    esp_netif_ip_info_t ip = {0};
    if (ap_address(&ip) != 0 || stop_requested() || lw_wifi_ap_faults()) goto end;
    s->healthy_ap = true;
    socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (socket_fd < 0 || stop_requested()) goto end;
    int flags = fcntl(socket_fd, F_GETFL, 0);
    if (flags < 0 || stop_requested() ||
        fcntl(socket_fd, F_SETFL, flags | O_NONBLOCK) < 0 || stop_requested()) goto end;
    struct sockaddr_in local = {.sin_family = AF_INET,
        .sin_port = htons(LW_WIFI_COMMAND_PORT), .sin_addr.s_addr = ip.ip.addr};
    if (bind(socket_fd, (struct sockaddr *)&local, sizeof(local)) < 0 || stop_requested()) goto end;
    struct sockaddr_in actual = {0};
    socklen_t actual_size = sizeof(actual);
    if (getsockname(socket_fd, (struct sockaddr *)&actual, &actual_size) < 0 ||
        actual_size != sizeof(actual) || actual.sin_family != AF_INET ||
        !same_peer(&local, &actual) || stop_requested()) goto end;

    for (;;) {
        if (service(s, socket_fd) != 0) break;
        int64_t turn_start = esp_timer_get_time();
        for (unsigned count = 0; count < READS_PER_TURN; ++count) {
            int64_t now = esp_timer_get_time();
            if (now < turn_start || stop_requested() || lw_wifi_ap_faults()) goto end;
            if (now - turn_start >= TURN_US) break;
            struct sockaddr_in sender = {0};
            socklen_t sender_size = sizeof(sender);
            ssize_t size = recvfrom(socket_fd, s->wire, sizeof(s->wire), 0,
                                    (struct sockaddr *)&sender, &sender_size);
            int socket_error = errno;
            int64_t received_us = esp_timer_get_time();
            if (stop_requested() || lw_wifi_ap_faults()) goto end;
            if (size < 0) {
                if (socket_error == EAGAIN || socket_error == EWOULDBLOCK || socket_error == EINTR) break;
                goto end;
            }
            /* Pinned lwIP recvfrom returns copied length when truncated. The
             * extra byte makes every oversize datagram exceed WIRE_MAX. */
            if (size == 0 || size > WIRE_MAX || !valid_sender(&sender, sender_size, &ip)) continue;
            if (s->have_peer && !same_peer(&s->peer, &sender)) continue;
            if (!s->controller.owned) {
                if (received_us < 0 || received_us < s->setup_refill_us) goto end;
                if (s->setup_refill_us < 0) s->setup_refill_us = received_us;
                int64_t refill = (received_us - s->setup_refill_us) / SETUP_INTERVAL_US;
                if (refill) {
                    s->setup_tokens = refill >= 2 ? 2 :
                        (s->setup_tokens < 2 ? s->setup_tokens + 1 : 2);
                    s->setup_refill_us += refill * SETUP_INTERVAL_US;
                }
                /* Two-token burst admits HELLO followed immediately by CLAIM;
                 * replenish one per 10ms, never reset on admission expiry. */
                if (!s->setup_tokens) continue;
                --s->setup_tokens;
            }
            size_t written = 0;
            enum lw_session_result result = lw_controller_receive_observed(&s->controller,
                s->wire, (size_t)size, s->root, received_us,
                PIOS_LiteWing_PilotReadAdmissionMapping, healthy_random, s,
                s->reply, sizeof(s->reply), &written);
            if (result == LW_RETIRED || stop_requested() || lw_wifi_ap_faults()) goto end;
            if (result == LW_HANDSHAKE_REPLY) {
                if (!s->have_peer) {
                    if (s->controller.session.phase != LW_PENDING || s->controller.owned) goto end;
                    s->peer = sender;
                    s->have_peer = true;
                }
                if (send_reply(s, socket_fd, written) != 0) goto end;
            }
        }
        /* Time budget is checked between operations, not a preemption promise.
         * Expiry/challenges run without traffic; a hot socket cannot skip yield. */
        if (service(s, socket_fd) != 0) break;
        vTaskDelay(1);
    }
end:
    s->healthy_ap = false;
    lw_controller_fault(&s->controller);
    mbedtls_platform_zeroize(s->root, sizeof(s->root));
    mbedtls_platform_zeroize(s->wire, sizeof(s->wire));
    mbedtls_platform_zeroize(s->reply, sizeof(s->reply));
    bool ap_stopped = !ap_attempted;
    for (;;) {
        /* Pinned lwIP close retains the descriptor if prepare_delete fails.
         * Keep ownership for retry; EBADF establishes it is already absent. */
        if (socket_fd >= 0 && (close(socket_fd) == 0 || errno == EBADF)) socket_fd = -1;
        if (!ap_stopped) ap_stopped = lw_wifi_ap_stop(s->root) == 0;
        /* A rolled-back clock can prevent EndAdmission even after all radio
         * resources are gone. Retain the token/context and retry fault after
         * yielding; wiping it here would strand the receiver's UART guard. */
        if (socket_fd < 0 && ap_stopped && !s->controller.admission_guard) break;
        vTaskDelay(cleanup_delay());
        lw_controller_fault(&s->controller);
    }
    /* No release API is called. Receiver reservation survives this wipe/exit;
     * reboot is the v1 explicit recovery path after owning retirement. */
    mbedtls_platform_zeroize(s, sizeof(*s));
    /* Release publishes cleanup/wipes to acquire queries. No controller, AP,
     * socket or secret-buffer work is allowed after this acknowledgement.
     * Self-delete is only RTOS bookkeeping; it is not part of quiescence. */
    atomic_fetch_or_explicit(&lifecycle, COMMAND_QUIESCENT, memory_order_release);
    vTaskDelete(NULL);
}

int lw_wifi_command_start(void)
{
    unsigned expected = 0;
    if (!atomic_compare_exchange_strong(&lifecycle, &expected, COMMAND_RESERVED)) return -1;
    if (xTaskCreate(command_task, "lw-command", STACK_BYTES, NULL,
                    tskIDLE_PRIORITY + 1, NULL) != pdPASS) {
        expected = COMMAND_RESERVED;
        if (!atomic_compare_exchange_strong(&lifecycle, &expected, 0)) {
            /* Stop was requested during creation. No task exists on failure,
             * but resetting the word would lose the maintenance stop fence. */
            atomic_fetch_or_explicit(&lifecycle, COMMAND_QUIESCENT, memory_order_release);
        }
        return -1;
    }
    return 0;
}
