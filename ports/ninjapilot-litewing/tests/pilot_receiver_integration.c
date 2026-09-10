/* Real session, crypto and receiver; only platform clock/object storage mocked. */
#include "uavobjectmanager.h"
#include "pios_gcsrcvr_priv.h"
#include "pios_litewing_gcsrcvr.h"
#include "litewing_pilot_session.h"
#include "litewing_pilot_wire.h"
#include "pios_litewing_pilot_mac.h"
#include <string.h>

static int64_t clock_us = 1000;
static GCSReceiverData object;
static unsigned storage_writes;
int64_t esp_timer_get_time(void) { return clock_us; }
UAVObjHandle GCSReceiverHandle(void) { return &object; }
int32_t UAVObjUnpack(UAVObjHandle obj, uint16_t instance, const uint8_t *data)
{
    assert(obj == &object && instance == 0);
    memcpy(&object, data, sizeof(object));
    ++storage_writes;
    return 0;
}
static int random_bytes(void *ctx, uint8_t *out, size_t size)
{
    memset(out, ++*(unsigned *)ctx, size);
    return 0;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    uint32_t receiver_id;
    assert(PIOS_GCSRCVR_Init(&receiver_id) == 0);
    struct lw_pilot_session session;
    lw_session_init(&session);
    struct lw_pilot_mac_key root, key;
    memset(root.bytes, 'r', 32);
    struct lw_wire_frame frame = {0};
    frame.kind = 1; frame.payload_len = 32;
    memset(frame.payload, 'h', 32);
    uint8_t wire[594], reply[594], owner[16];
    size_t size, written;
    unsigned counter = 0;
    assert(lw_wire_encode(&frame, lw_pilot_mac, &root, wire, sizeof(wire), &size) == 0);
    assert(lw_session_receive(&session, wire, size, root.bytes, 1000, 1, 1,
        random_bytes, &counter, reply, sizeof(reply), &written) == LW_HANDSHAKE_REPLY);
    memset(&frame, 0, sizeof(frame));
    frame.kind = 3; frame.sequence = 1;
    memcpy(frame.session, session.session, 16);
    memcpy(owner, session.session, 16);
    memcpy(frame.challenge, session.challenge, 16);
    memcpy(key.bytes, session.keys.c2b, 32);
    assert(lw_wire_encode(&frame, lw_pilot_mac, &key, wire, sizeof(wire), &size) == 0);
    assert(lw_session_receive(&session, wire, size, root.bytes, 1100, 1, 1,
        random_bytes, &counter, reply, sizeof(reply), &written) == LW_HANDSHAKE_REPLY);
    clock_us = !strcmp(argv[1], "rollback") ? 5000 : 1200;
    assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(owner, 1) == 0);
    frame.kind = 5; frame.sequence = 2; frame.payload_len = 16;
    const uint8_t channels[16] = {3,232,7,208,3,233,7,207,4,210,6,31,6,253,4,76};
    memcpy(frame.payload, channels, 16);
    assert(lw_wire_encode(&frame, lw_pilot_mac, &key, wire, sizeof(wire), &size) == 0);
    assert(lw_session_prepare_control(&session, wire, size, 2000) == LW_PILOT_CANDIDATE);
    clock_us = 3000;
    if (!strcmp(argv[1], "released")) {
        assert(PIOS_LiteWing_GCSReceiver_ReleaseWireless(owner,1)==0);
        clock_us=4000;
        GCSReceiverData usb={.Channel={1600}};
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(const uint8_t *)&usb,clock_us)==0);
        assert(PIOS_LiteWing_GCSReceiver_PublishWireless(owner,&session)==-1);
        assert(session.phase==LW_CLOSED);
        assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,0)==1600);
        assert(storage_writes==1);
        return 0;
    } else if (!strcmp(argv[1], "delayed") || !strcmp(argv[1], "rollback")) {
        if (!strcmp(argv[1], "delayed")) clock_us = 76001;
        assert(PIOS_LiteWing_GCSReceiver_PublishWireless(owner, &session) == -1);
        assert(session.phase == LW_CLOSED);
    } else if (!strcmp(argv[1], "wrong-owner")) {
        uint8_t other[16] = {99};
        assert(PIOS_LiteWing_GCSReceiver_PublishWireless(other, &session) == -1);
        assert(session.phase == LW_CLOSED);
    } else {
        assert(PIOS_LiteWing_GCSReceiver_PublishWireless(owner, &session) == 0);
        const uint16_t expected[8] = {1000,2000,1001,1999,1234,1567,1789,1100};
        for (unsigned i=0;i<8;++i) assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,i)==expected[i]);
        assert(storage_writes == 0); /* Wireless is never general UAVObjUnpack. */
        if (!strcmp(argv[1], "stop")) {
            frame.kind = 6; frame.sequence = 3; frame.payload_len = 0;
            assert(lw_wire_encode(&frame,lw_pilot_mac,&key,wire,sizeof(wire),&size)==0);
            assert(lw_session_prepare_control(&session,wire,size,4000)==LW_RETIRED);
            clock_us=4000;
            assert(PIOS_LiteWing_GCSReceiver_PublishWireless(owner,&session)==-1);
        } else {
            assert(!strcmp(argv[1], "publish"));
            clock_us=100999;
            assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,0)==1000);
            clock_us=101000;
        }
    }
    assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,0)==PIOS_RCVR_TIMEOUT);
    GCSReceiverData usb = {.Channel={1500}};
    assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(const uint8_t *)&usb,clock_us)==-1);
    assert(storage_writes == 0); /* Failure/STOP does not transfer to USB. */
    return 0;
}
