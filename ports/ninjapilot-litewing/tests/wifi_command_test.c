#define _POSIX_C_SOURCE 200809L
/* Actual task body + real protocol/controller/receiver. Only external platform
 * boundaries are fixtures. No simulated authentication or receiver ownership. */
#include "uavobjectmanager.h"
#include "pios_gcsrcvr_priv.h"
#include "pios_litewing_gcsrcvr.h"
#include "pios_litewing_wifi_command.h"
#include "pios_litewing_wifi_ap.h"
#include "pios_litewing_pilot_mapping.h"
#include "litewing_pilot_controller.h"
#include "litewing_pilot_wire.h"
#include "pios_litewing_pilot_mac.h"
#include "freertos/task.h"
#include "esp_netif.h"
#include "lwip/sockets.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#undef socket
#undef fcntl
#undef bind
#undef getsockname
#undef recvfrom
#undef sendto
#undef close

/* Observe real controller entry for setup work bounds and cleanup checks. */
#define lw_controller_receive_observed fixture_real_receive_observed
#include "../target/litewing_pilot_controller.c"
#undef lw_controller_receive_observed

static const char *scenario;
static TaskFunction_t task_body;
static void *task_arg;
static int creates, ap_starts, ap_stops, radio, socket_open, closed, deleted;
static int close_attempts;
static int stage, malformed, peer_attacks, published, fault, rng_calls, reads;
static int turns, turn_reads, max_reads, setup_calls, proofs, accepts, nonblocking;
static int64_t now = 1000, first_setup;
static uint32_t receiver;
static GCSReceiverData object;
static struct sockaddr_in bound;
static struct lw_wire_frame proof;
static struct lw_session_keys keys;
static struct lw_pilot_controller *observed;
static struct lw_pilot_mac_key root = {.bytes = {'r'}};
static bool is(const char *name) { return !strcmp(scenario, name); }
static bool loopback(void) { return !strncmp(scenario, "loopback-", 9); }
static void zeros(const void *data, size_t size) {
    const unsigned char *p = data;
    for (size_t i = 0; i < size; ++i) assert(p[i] == 0);
}
enum lw_session_result lw_controller_receive_observed(struct lw_pilot_controller *c,
    const uint8_t *wire, size_t size, const uint8_t key[32], int64_t received,
    lw_pilot_mapping_reader mapping, lw_session_rng rng, void *ctx,
    uint8_t *reply, size_t capacity, size_t *written) {
    observed = c;
    if (!c->owned) {
        if (!setup_calls) first_setup = now;
        ++setup_calls;
        assert(setup_calls <= 2 + (now - first_setup) / 10000);
    }
    assert(radio && !fault && mapping == PIOS_LiteWing_PilotReadAdmissionMapping);
    enum lw_session_result result = fixture_real_receive_observed(c, wire, size, key,
        received, mapping, rng, ctx, reply, capacity, written);
    if (loopback() && result == LW_PILOT_CANDIDATE) {
        assert(pios_gcsrcvr_rcvr_driver.read(receiver, 0) == 1000);
        published = 1;
    }
    return result;
}
int64_t esp_timer_get_time(void) {
    if (loopback()) {
        struct timespec clock; assert(clock_gettime(CLOCK_MONOTONIC, &clock) == 0);
        now = (int64_t)clock.tv_sec * 1000000 + clock.tv_nsec / 1000;
    }
    return now;
}
UAVObjHandle GCSReceiverHandle(void) { return &object; }
int32_t UAVObjUnpack(UAVObjHandle h, uint16_t instance, const uint8_t *data) {
    assert(h == &object && instance == 0); memcpy(&object, data, sizeof(object)); return 0;
}
int PIOS_LiteWing_PilotReadAdmissionMapping(struct lw_pilot_channel out[5]) {
    ++reads;
    for (unsigned i = 0; i < 5; ++i) out[i] = (struct lw_pilot_channel){i+1,1000,1500,2000};
    return 0;
}
BaseType_t xTaskCreate(TaskFunction_t body, const char *name, uint32_t stack,
    void *arg, UBaseType_t priority, TaskHandle_t *handle) {
    (void)name; (void)handle; assert(!ap_starts && stack >= 8192 && priority == 1);
    ++creates; if (is("create")) return 0;
    task_body = body; task_arg = arg; return pdPASS;
}
void vTaskDelay(TickType_t ticks) {
    assert(ticks >= 1); ++turns;
    if (loopback()) {
        struct timespec delay = {.tv_sec = ticks / 1000, .tv_nsec = (ticks % 1000) * 1000000};
        assert(nanosleep(&delay, NULL) == 0);
    }
    assert(turn_reads <= 4); if (turn_reads > max_reads) max_reads = turn_reads;
    turn_reads = 0; now += (int64_t)ticks * 1000;
    assert(turns < 3000);
    if ((is("flood") || is("time-budget")) && turns == 150) fault = 1;
    if (is("clock-rollback") && published) now = 500;
}
void vTaskDelete(TaskHandle_t handle) {
    assert(handle == NULL && !socket_open && !radio);
    if (observed) zeros(observed, sizeof(*observed));
    ++deleted;
}
int lw_wifi_ap_start(uint8_t out[32]) {
    ++ap_starts; assert(creates == 1);
    if (is("missing")) { memset(out, 0, 32); return -1; }
    radio = 1; memcpy(out, root.bytes, 32); return 0;
}
int lw_wifi_ap_stop(uint8_t out[32]) {
    ++ap_stops; zeros(out, 32);
    if (is("cleanup") && ap_stops < 4) return -1;
    radio = 0; return 0;
}
unsigned lw_wifi_ap_faults(void) { return fault ? LW_WIFI_AP_STATION_LOST : 0; }
void esp_fill_random(void *out, size_t n) {
    assert(radio && !fault); memset(out, ++rng_calls, n);
    if (is("rng-fault")) fault = 1;
}
struct esp_netif_obj { int unused; } ap;
esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key) {
    assert(radio && !strcmp(key, "WIFI_AP_DEF")); return is("netif") ? NULL : &ap;
}
bool esp_netif_is_netif_up(esp_netif_t *n) { assert(n == &ap); return !is("not-up"); }
esp_err_t esp_netif_get_ip_info(esp_netif_t *n, esp_netif_ip_info_t *out) {
    assert(n == &ap); out->ip.addr = is("zero-ip") ? 0 : htonl(loopback() ? 0x7f000001 : 0xc0a80401);
    out->netmask.addr = htonl(loopback() ? 0xff000000 : 0xffffff00); out->gw = out->ip;
    return is("ip") ? -1 : ESP_OK;
}
int fixture_socket(int family, int type, int protocol) {
    assert(radio && family == AF_INET && type == SOCK_DGRAM && protocol == IPPROTO_UDP);
    if (is("socket")) return -1;
    socket_open = 1;
    if (loopback()) return socket(family, type, protocol);
    return 7;
}
int fixture_fcntl(int fd, int cmd, ...) {
    assert(socket_open);
    if (loopback() && cmd == F_GETFL) return fcntl(fd, cmd, 0);
    if (cmd == F_GETFL) return is("fcntl-get") ? -1 : 0;
    assert(cmd == F_SETFL);
    va_list args; va_start(args, cmd); int flags = va_arg(args, int); va_end(args);
    assert(flags & O_NONBLOCK); if (is("fcntl-set")) return -1;
    nonblocking = 1;
    return loopback() ? fcntl(fd, cmd, flags) : 0;
}
int fixture_bind(int fd, const struct sockaddr *address, socklen_t size) {
    assert(nonblocking && size == sizeof(bound));
    memcpy(&bound, address, size);
    if (loopback()) {
        assert(bound.sin_addr.s_addr == htonl(0x7f000001));
        return bind(fd, address, size);
    }
    assert(bound.sin_family == AF_INET && bound.sin_addr.s_addr == htonl(0xc0a80401));
    assert(ntohs(bound.sin_port) == LW_WIFI_COMMAND_PORT);
    return is("bind") ? -1 : 0;
}
int fixture_getsockname(int fd, struct sockaddr *address, socklen_t *size) {
    if (loopback()) {
        int result = getsockname(fd, address, size);
        if (!result) { printf("%u\n", ntohs(((struct sockaddr_in *)address)->sin_port)); fflush(stdout); }
        return result;
    }
    assert(fd == 7 && *size >= sizeof(bound));
    memcpy(address, &bound, sizeof(bound)); *size = sizeof(bound);
    if (is("wrong-bind")) ((struct sockaddr_in *)address)->sin_addr.s_addr = 0;
    return is("getsockname") ? -1 : 0;
}
static size_t encode(uint8_t *out, size_t capacity, int kind, uint64_t sequence) {
    struct lw_wire_frame frame = {0};
    struct lw_pilot_mac_key key = root;
    frame.kind = kind; frame.sequence = sequence;
    if (kind == 1) { frame.payload_len = 32; memset(frame.payload, 'h', 32); }
    else {
        memcpy(key.bytes, keys.c2b, 32); memcpy(frame.session, proof.session, 16);
        memcpy(frame.challenge, proof.challenge, 16);
        if (kind != 6) {
            frame.payload_len = 16;
            for (int i = 0; i < 8; ++i) { frame.payload[2*i] = 5; frame.payload[2*i+1] = 220; }
            if (kind == 3) { frame.payload[0] = 3; frame.payload[1] = 232; }
        }
    }
    size_t size;
    assert(lw_wire_encode(&frame, lw_pilot_mac, &key, out, capacity, &size) == 0);
    return size;
}
ssize_t fixture_recvfrom(int fd, void *out, size_t capacity, int flags,
                        struct sockaddr *address, socklen_t *length) {
    if (loopback()) { ++turn_reads; return recvfrom(fd, out, capacity, flags, address, length); }
    assert(fd == 7 && nonblocking && capacity == 595 && flags == 0);
    ++turn_reads; now += is("time-budget") ? 800 : 100;
    struct sockaddr_in sender = {.sin_family = AF_INET, .sin_port = htons(42000),
        .sin_addr.s_addr = htonl(0xc0a80402)};
    assert(*length >= sizeof(sender)); *length = sizeof(sender);
    if (stage == 0 && is("malformed") && malformed++ < 4) {
        memcpy(address, &sender, sizeof(sender)); memset(out, 0, capacity);
        if (malformed == 1) return 595;
        if (malformed == 2) return 0;
        if (malformed == 3) { *length = 0; return encode(out, capacity, 1, 0); }
        ((struct sockaddr_in *)address)->sin_port = 0;
        return encode(out, capacity, 1, 0);
    }
    memcpy(address, &sender, sizeof(sender));
    if (is("flood") || is("time-budget")) {
        size_t size = encode(out, capacity, 1, 0); ((uint8_t *)out)[size-1] ^= 1; return size;
    }
    if (stage == 0) return encode(out, capacity, 1, 0);
    if (stage == 1) {
        if (is("pending-peer") && peer_attacks++ == 0) {
            ((struct sockaddr_in *)address)->sin_port = htons(43000);
            return encode(out, capacity, 3, 1);
        }
        if (is("pending-expiry") && now < 1010000) { errno = EAGAIN; return -1; }
        if (is("pending-expiry") && proofs > 1 && now >= 1010000) {
            ((struct sockaddr_in *)address)->sin_port = htons(43000);
            return encode(out, capacity, 1, 0);
        }
        return encode(out, capacity, 3, 1);
    }
    if (stage == 2) { stage = 3; return encode(out, capacity, 5, 2); }
    if (!published) {
        assert(pios_gcsrcvr_rcvr_driver.read(receiver, 0) == 1500); published = 1;
    }
    if (is("recv-error")) { errno = EIO; return -1; }
    if (is("ap-fault") || is("cleanup")) fault = 1;
    if (is("loss") || is("ap-fault") || is("cleanup") || is("challenge-send") || is("clock-rollback")) {
        errno = EAGAIN; return -1;
    }
    if (is("peer-replay") && peer_attacks++ < 3) {
        if (peer_attacks == 1) ((struct sockaddr_in *)address)->sin_port = htons(43000);
        if (peer_attacks == 2) ((struct sockaddr_in *)address)->sin_addr.s_addr = htonl(0xc0a80403);
        assert(pios_gcsrcvr_rcvr_driver.read(receiver, 0) == 1500);
        return encode(out, capacity, peer_attacks == 3 ? 5 : 6, peer_attacks == 3 ? 2 : 3);
    }
    return encode(out, capacity, 6, 3);
}
ssize_t fixture_sendto(int fd, const void *wire, size_t size, int flags,
                      const struct sockaddr *address, socklen_t length) {
    if (loopback()) return sendto(fd, wire, size, flags, address, length);
    assert(fd == 7 && radio && !fault && flags == 0 && length == sizeof(struct sockaddr_in));
    const struct sockaddr_in *peer = (const struct sockaddr_in *)address;
    assert(peer->sin_addr.s_addr == htonl(0xc0a80402));
    assert(peer->sin_port == htons(is("pending-expiry") && now >= 1010000 ? 43000 : 42000));
    struct lw_pilot_mac_key key = root;
    if (stage >= 2 || (size > 6 && ((const uint8_t *)wire)[6] == 4)) memcpy(key.bytes, keys.b2c, 32);
    struct lw_wire_frame response;
    assert(lw_wire_decode(wire, size, 1, lw_pilot_mac, &key, &response) == 0);
    if (response.kind == 2) {
        ++proofs; proof = response;
        if (response.payload_len == 64) {
            assert(lw_pilot_derive_keys(root.bytes, response.payload, response.payload+32,
                                      response.session, &keys) == 0);
            stage = 1;
            if (is("pending-expiry") && now >= 1010000) { fault = 1; return size; }
        }
        if (is("hello-send") || (is("challenge-send") && stage >= 2)) { errno = EAGAIN; return -1; }
    } else {
        assert(response.kind == 4); ++accepts; stage = 2;
        if (is("accept-send")) return size - 1;
    }
    return (ssize_t)size;
}
int fixture_close(int fd) {
    if (loopback()) { int result = close(fd); if (!result) socket_open = 0; return result; }
    assert(fd == 7 && socket_open); ++close_attempts;
    if (is("close-error") && close_attempts < 3) { errno = EIO; return -1; }
    socket_open = 0; ++closed; return 0;
}
int main(int argc, char **argv) {
    assert(argc == 2); scenario = argv[1]; memset(root.bytes, 'r', 32);
    assert(PIOS_GCSRCVR_Init(&receiver) == 0);
    int result = lw_wifi_command_start();
    if (is("create")) {
        assert(result == -1 && creates == 1 && ap_starts == 0);
        assert(lw_wifi_command_start() == -1 && creates == 2 && ap_starts == 0); return 0;
    }
    assert(result == 0 && task_body && !ap_starts);
    assert(lw_wifi_command_start() == -1 && creates == 1);
    task_body(task_arg);
    assert(deleted == 1 && ap_starts == 1 && ap_stops >= 1);
    assert(lw_wifi_command_start() == -1 && creates == 1);
    if (accepts) {
        assert(pios_gcsrcvr_rcvr_driver.read(receiver, 0) == PIOS_RCVR_TIMEOUT);
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&object, 0, (uint8_t *)&object, now) == -1);
    }
    if (is("stop") || is("loss") || is("peer-replay") || is("malformed") ||
        is("ap-fault") || is("cleanup") || is("recv-error") || is("challenge-send")) assert(published);
    if (is("flood") || is("time-budget")) {
        assert(setup_calls > 2 && setup_calls <= (now / 10000 + 2));
        assert(!reads && !rng_calls && !proofs && max_reads <= 4);
        if (is("time-budget")) assert(max_reads <= 3);
    }
    if (is("cleanup")) assert(ap_stops == 4 && turns >= 3);
    if (is("close-error")) assert(close_attempts == 3 && closed == 1 && turns >= 2);
    if (is("pending-expiry")) assert(now >= 1010000 && !accepts && proofs > 1);
    if (loopback()) {
        assert(published && pios_gcsrcvr_rcvr_driver.read(receiver, 0) == PIOS_RCVR_TIMEOUT);
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&object, 0, (uint8_t *)&object, now) == -1);
    }
    puts("command task fixture passed"); return 0;
}
