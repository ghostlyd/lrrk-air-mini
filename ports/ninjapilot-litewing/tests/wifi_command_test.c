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
#include "litewing_telemetry_wire.h"
#include "pios_litewing_pilot_mac.h"
#include "freertos/task.h"
#include "esp_netif.h"
#include "lwip/sockets.h"
#include <errno.h>
#include <math.h>
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

/* Include the unchanged task body with an observing wipe boundary. The real
 * mbedTLS wipe still runs; an early acknowledgement fails at the first wipe,
 * even if the task would wipe everything before reaching vTaskDelete. */
static void fixture_command_zeroize(void *data, size_t size) {
    assert(!lw_wifi_command_is_quiescent());
    mbedtls_platform_zeroize(data, size);
}
static int fixture_telemetry_mac(void *, const uint8_t *, size_t, uint8_t[32]);
#define lw_pilot_mac fixture_telemetry_mac
#define mbedtls_platform_zeroize fixture_command_zeroize
#define socket fixture_socket
#define fcntl fixture_fcntl
#define bind fixture_bind
#define getsockname fixture_getsockname
#define recvfrom fixture_recvfrom
#define sendto fixture_sendto
#define close fixture_close
#include "../target/pios_litewing_wifi_command.c"
#undef lw_pilot_mac
#undef mbedtls_platform_zeroize
#undef socket
#undef fcntl
#undef bind
#undef getsockname
#undef recvfrom
#undef sendto
#undef close

static const char *scenario;
static TaskFunction_t task_body;
static void *task_arg;
static int creates, ap_starts, ap_stops, radio, socket_open, closed, deleted;
static int close_attempts;
static int stop_requests;
static uint8_t *task_root;
static unsigned admission_parks;
static uint64_t parked_guard;
static int stage, malformed, peer_attacks, published, fault, rng_calls, reads;
static int turns, turn_reads, max_reads, setup_calls, proofs, accepts, nonblocking;
static int64_t now = 1000, first_setup;
static int telemetry_reads, telemetry_sends;
static int64_t telemetry_started, last_telemetry_send = -1;
static uint64_t telemetry_sequence, control_sequence = 2;
static uint32_t receiver;
static GCSReceiverData object;
static struct sockaddr_in bound;
static struct lw_wire_frame proof;
static struct lw_session_keys keys;
static struct lw_pilot_controller *observed;
static struct lw_pilot_mac_key root = {.bytes = {'r'}};
static bool is(const char *name) { return !strcmp(scenario, name); }
static bool loopback(void) { return !strncmp(scenario, "loopback-", 9); }
static bool telemetry_case(void) { return !strncmp(scenario, "telemetry-", 10); }
static void request_retirement(void) {
    assert(!lw_wifi_command_is_quiescent());
    int old_turns = turns, old_stops = ap_stops, old_closes = close_attempts;
    lw_wifi_command_request_stop();
    lw_wifi_command_request_stop();
    ++stop_requests;
    assert(turns == old_turns && ap_stops == old_stops && close_attempts == old_closes);
    assert(!lw_wifi_command_is_quiescent());
    assert(lw_wifi_command_start() == -1);
}
static int fixture_telemetry_mac(void *ctx, const uint8_t *message, size_t length, uint8_t tag[32]) {
    int result = lw_pilot_mac(ctx, message, length, tag);
    assert(length > 6 && message[6] == 8);
    if (is("telemetry-mac-expire")) now += 100000;
    if (is("telemetry-mac-slow")) now += 2001;
    if (is("telemetry-mac-stop")) request_retirement();
    return result;
}
static void zeros(const void *data, size_t size) {
    const unsigned char *p = data;
    for (size_t i = 0; i < size; ++i) assert(p[i] == 0);
}
enum lw_session_result lw_controller_receive_observed(struct lw_pilot_controller *c,
    const uint8_t *wire, size_t size, const uint8_t key[32], int64_t received,
    lw_pilot_mapping_reader mapping, lw_session_rng rng, void *ctx,
    uint8_t *reply, size_t capacity, size_t *written) {
    observed = c;
    assert(!lw_wifi_command_is_quiescent() && !stop_requests);
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
/* Only the object-read platform boundary is substituted. Framing, keys,
 * owner expiry and task scheduling remain production code. */
int lw_telemetry_read(unsigned index, struct lw_telemetry_record *out) {
    static const uint32_t ids[] = {0xD7E0D964,0xEF69B6BC,0x26962352,0x6B7639EC,0xB8229FE4};
    static const uint16_t sizes[] = {28,8,30,25,29};
    assert(index == (unsigned)telemetry_reads % 5);
    ++telemetry_reads;
    assert(observed && observed->owned && observed->session.phase == LW_ACTIVE);
    if (is("telemetry-stop")) request_retirement();
    if (is("telemetry-expire")) now += 100000;
    if (is("telemetry-slow")) now += 2001;
    if (is("telemetry-rollback")) now = 500;
    *out = (struct lw_telemetry_record){.object_id=ids[index], .data_len=sizes[index],
        .serialized_us=(uint64_t)esp_timer_get_time(), .sample_age_us=UINT64_MAX};
    if (index == 0) {
        float attitude[7] = {1,0,0,0,1.25f,-2.5f,3.75f};
        memcpy(out->data,attitude,sizeof(attitude));
    }
    if (index == 2) {
        float battery[7] = {3.8f,NAN,NAN,NAN,NAN,NAN,NAN};
        memcpy(out->data,battery,sizeof(battery)); out->data[28]=1;
    }
    if (index == 3) { memset(out->data,1,21); out->data[0]=2; }
    if (index == 4) {
        uint16_t actuators[4] = {11,22,33,44};
        memcpy(out->data,actuators,sizeof(actuators));
    }
    if (!strncmp(scenario,"loopback-omit-",14) && scenario[14] == (char)('0'+index)) return -1;
    return is("telemetry-busy") ? -1 : 0;
}
UAVObjHandle GCSReceiverHandle(void) { return &object; }
int32_t UAVObjUnpack(UAVObjHandle h, uint16_t instance, const uint8_t *data) {
    assert(h == &object && instance == 0); memcpy(&object, data, sizeof(object)); return 0;
}
int PIOS_LiteWing_PilotReadAdmissionMapping(struct lw_pilot_channel out[5]) {
    ++reads;
    /* Second read is inside the real admission exclusion. Roll back below its
     * USB fence so controller_fault cannot end admission until clock recovery. */
    if (is("admission-rollback") && reads == 2) now = 500;
    if (is("mapping-stop") && reads == 2) request_retirement();
    for (unsigned i = 0; i < 5; ++i) out[i] = (struct lw_pilot_channel){i+1,1000,1500,2000};
    return 0;
}
BaseType_t xTaskCreate(TaskFunction_t body, const char *name, uint32_t stack,
    void *arg, UBaseType_t priority, TaskHandle_t *handle) {
    (void)name; (void)handle; assert(!ap_starts && stack >= 8192 && priority == 1);
    assert(!lw_wifi_command_is_quiescent());
    ++creates;
    if (is("create-stop-success") || is("create-stop-failure")) request_retirement();
    if (is("create") || is("create-stop-failure")) return 0;
    task_body = body; task_arg = arg;
    if (is("create-complete-before-return")) {
        request_retirement();
        body(arg);
        assert(lw_wifi_command_is_quiescent());
    }
    return pdPASS;
}
void vTaskDelay(TickType_t ticks) {
    assert(!lw_wifi_command_is_quiescent());
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
    if (is("maintenance-stuck") && ap_stops) {
        assert(!deleted && !socket_open && observed && observed->owned);
        assert(observed->session.phase == LW_CLOSED);
        zeros(&observed->session.keys, sizeof(observed->session.keys));
        request_retirement();
    }
    if (is("admission-rollback")) {
        assert(ticks >= pdMS_TO_TICKS(100));
        assert(!socket_open && !radio && closed == 1 && ap_stops == 1 && !deleted);
        assert(observed && observed->admission_guard && !observed->owned);
        assert(observed->session.phase == LW_CLOSED);
        zeros(&observed->session.keys, sizeof(observed->session.keys));
        if (!admission_parks) parked_guard = observed->admission_guard;
        assert(observed->admission_guard == parked_guard);
        now = 500;
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&object, 0, (uint8_t *)&object, now) == -1);
        /* Repeated failure must retain context and yield, even with all radio
         * resources gone. Ordinary clock recovery then permits EndAdmission. */
        if (++admission_parks == 3) now = 5000;
    }
}
void vTaskDelete(TaskHandle_t handle) {
    assert(handle == NULL && !socket_open && !radio);
    assert(lw_wifi_command_is_quiescent());
    if (task_root) zeros(task_root, 32);
    lw_wifi_command_request_stop();
    lw_wifi_command_request_stop();
    assert(lw_wifi_command_is_quiescent());
    if (is("admission-rollback")) {
        assert(admission_parks == 3 && reads == 2 && !accepts);
        ++now; /* Fresh UART arrival must be strictly after the cleanup fence. */
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&object, 0, (uint8_t *)&object, now) == 0);
    }
    if (observed) zeros(observed, sizeof(*observed));
    ++deleted;
}
int lw_wifi_ap_start(uint8_t out[32]) {
    assert(!lw_wifi_command_is_quiescent() && !stop_requests);
    task_root = out;
    ++ap_starts; assert(creates == 1);
    if (is("missing")) { memset(out, 0, 32); return -1; }
    radio = 1; memcpy(out, root.bytes, 32);
    if (is("ap-start-stop")) request_retirement();
    return 0;
}
int lw_wifi_ap_stop(uint8_t out[32]) {
    assert(!lw_wifi_command_is_quiescent());
    ++ap_stops; zeros(out, 32);
    if (is("cleanup-stop")) {
        request_retirement();
        if (ap_stops < 4) return -1;
    }
    if (is("maintenance-stuck") && ap_stops < 26) return -1;
    if (is("cleanup") && ap_stops < 4) return -1;
    radio = 0; return 0;
}
unsigned lw_wifi_ap_faults(void) {
    assert(!lw_wifi_command_is_quiescent());
    return fault ? LW_WIFI_AP_STATION_LOST : 0;
}
void esp_fill_random(void *out, size_t n) {
    assert(radio && !fault); memset(out, ++rng_calls, n);
    assert(!lw_wifi_command_is_quiescent() && !stop_requests);
    if (is("rng-stop")) request_retirement();
    if (is("rng-fault")) fault = 1;
}
struct esp_netif_obj { int unused; } ap;
esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key) {
    assert(!lw_wifi_command_is_quiescent() && !stop_requests);
    assert(radio && !strcmp(key, "WIFI_AP_DEF")); return is("netif") ? NULL : &ap;
}
bool esp_netif_is_netif_up(esp_netif_t *n) {
    assert(n == &ap && !lw_wifi_command_is_quiescent() && !stop_requests);
    if (is("ready-stop")) { request_retirement(); return false; }
    return !is("not-up");
}
esp_err_t esp_netif_get_ip_info(esp_netif_t *n, esp_netif_ip_info_t *out) {
    assert(n == &ap); out->ip.addr = is("zero-ip") ? 0 : htonl(loopback() ? 0x7f000001 : 0xc0a80401);
    out->netmask.addr = htonl(loopback() ? 0xff000000 : 0xffffff00); out->gw = out->ip;
    return is("ip") ? -1 : ESP_OK;
}
int fixture_socket(int family, int type, int protocol) {
    assert(!lw_wifi_command_is_quiescent() && !stop_requests);
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
    assert(!lw_wifi_command_is_quiescent() && !stop_requests);
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
        telemetry_started = now;
    }
    if (telemetry_case()) {
        if (now - telemetry_started < 650000)
            return encode(out, capacity, 5, ++control_sequence);
        return encode(out, capacity, 6, ++control_sequence);
    }
    if (is("active-stop") || is("maintenance-stuck")) {
        request_retirement();
        return encode(out, capacity, 5, 3);
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
    assert(!lw_wifi_command_is_quiescent() && !stop_requests);
    if (loopback()) return sendto(fd, wire, size, flags, address, length);
    assert(fd == 7 && radio && !fault && flags == 0 && length == sizeof(struct sockaddr_in));
    const struct sockaddr_in *peer = (const struct sockaddr_in *)address;
    assert(peer->sin_addr.s_addr == htonl(0xc0a80402));
    assert(peer->sin_port == htons(is("pending-expiry") && now >= 1010000 ? 43000 : 42000));
    struct lw_pilot_mac_key key = root;
    if (stage >= 2 || (size > 6 && ((const uint8_t *)wire)[6] == 4)) memcpy(key.bytes, keys.b2c, 32);
    bool telemetry = size > 6 && ((const uint8_t *)wire)[6] == 8;
    if (telemetry) memcpy(key.bytes, keys.telemetry, 32);
    struct lw_wire_frame response;
    assert(lw_wire_decode(wire, size, 1, lw_pilot_mac, &key, &response) == 0);
    if (telemetry) {
        struct lw_telemetry_record record;
        assert(lw_telemetry_frame_validate(&response, &record) == 0);
        assert(observed && observed->owned && observed->session.phase == LW_ACTIVE);
        assert(!memcmp(response.session, observed->session.session, 16));
        assert(response.sequence == ++telemetry_sequence);
        assert(last_telemetry_send < 0 || now-last_telemetry_send >= 100000);
        last_telemetry_send = now;
        ++telemetry_sends;
        /* A control/root key must not authenticate the telemetry packet. */
        memcpy(key.bytes, keys.b2c, 32);
        assert(lw_wire_decode(wire,size,1,lw_pilot_mac,&key,&response) != 0);
        memcpy(key.bytes, root.bytes, 32);
        assert(lw_wire_decode(wire,size,1,lw_pilot_mac,&key,&response) != 0);
        if (is("telemetry-eagain")) { errno=EAGAIN; return -1; }
        if (is("telemetry-eintr")) { errno=EINTR; return -1; }
        if (is("telemetry-error")) { errno=EIO; return -1; }
        if (is("telemetry-short")) return size-1;
        return size;
    }
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
    assert(!lw_wifi_command_is_quiescent());
    if (loopback()) { int result = close(fd); if (!result) socket_open = 0; return result; }
    assert(fd == 7 && socket_open); ++close_attempts;
    if (is("close-stop")) {
        request_retirement();
        if (close_attempts < 3) { errno = EIO; return -1; }
    }
    if (is("close-error") && close_attempts < 3) { errno = EIO; return -1; }
    socket_open = 0; ++closed; return 0;
}
int main(int argc, char **argv) {
    assert(argc == 2); scenario = argv[1]; memset(root.bytes, 'r', 32);
    assert(PIOS_GCSRCVR_Init(&receiver) == 0);
    assert(!lw_wifi_command_is_quiescent());
    if (is("stop-before-start")) {
        lw_wifi_command_request_stop();
        assert(lw_wifi_command_is_quiescent());
        lw_wifi_command_request_stop();
        assert(lw_wifi_command_is_quiescent() && lw_wifi_command_start() == -1);
        assert(!creates && !ap_starts && !ap_stops); return 0;
    }
    int result = lw_wifi_command_start();
    if (is("create")) {
        assert(result == -1 && creates == 1 && ap_starts == 0);
        assert(lw_wifi_command_start() == -1 && creates == 2 && ap_starts == 0); return 0;
    }
    if (is("create-stop-failure")) {
        assert(result == -1 && creates == 1 && !ap_starts && !ap_stops);
        assert(lw_wifi_command_is_quiescent());
        assert(lw_wifi_command_start() == -1 && creates == 1); return 0;
    }
    assert(result == 0 && task_body && !ap_starts);
    assert(lw_wifi_command_start() == -1 && creates == 1);
    if (is("queued-stop")) request_retirement();
    if (!is("create-complete-before-return")) task_body(task_arg);
    assert(deleted == 1 && lw_wifi_command_is_quiescent());
    if (is("queued-stop") || is("create-stop-success") || is("create-complete-before-return"))
        assert(!ap_starts && !ap_stops);
    else assert(ap_starts == 1 && ap_stops >= 1);
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
    if (is("close-stop")) assert(close_attempts == 3 && closed == 1 && stop_requests == 3);
    if (is("cleanup-stop")) assert(ap_stops == 4 && stop_requests == 4);
    if (is("maintenance-stuck")) assert(ap_stops == 26 && now >= 2500000 && published && accepts);
    if (is("active-stop")) assert(published && accepts && stop_requests == 1);
    if (is("mapping-stop")) assert(reads == 2 && !rng_calls && !accepts && !proofs);
    if (is("rng-stop")) assert(rng_calls == 1 && !accepts && !proofs);
    if (is("ap-start-stop") || is("ready-stop")) assert(stop_requests == 1 && !closed && !rng_calls);
    if (is("pending-expiry")) assert(now >= 1010000 && !accepts && proofs > 1);
    if (loopback()) {
        assert(published && pios_gcsrcvr_rcvr_driver.read(receiver, 0) == PIOS_RCVR_TIMEOUT);
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&object, 0, (uint8_t *)&object, now) == -1);
    }
    if (telemetry_case()) {
        assert(telemetry_reads > 0);
        if (is("telemetry-stream") || is("telemetry-eagain") || is("telemetry-eintr"))
            assert(telemetry_reads >= 6 && telemetry_sends == telemetry_reads);
        if (is("telemetry-busy") || is("telemetry-slow") || is("telemetry-mac-slow"))
            assert(telemetry_reads >= 6 && telemetry_sends == 0);
        if (is("telemetry-stop") || is("telemetry-expire") || is("telemetry-rollback") ||
            is("telemetry-mac-expire") || is("telemetry-mac-stop"))
            assert(telemetry_reads == 1 && telemetry_sends == 0);
        if (is("telemetry-short") || is("telemetry-error"))
            assert(telemetry_reads == 1 && telemetry_sends == 1);
    }
    puts("command task fixture passed"); return 0;
}
