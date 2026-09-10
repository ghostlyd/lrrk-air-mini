/* Removing admission checks, publication, or failure invalidation breaks this. */
#include "uavobjectmanager.h"
#include "pios_gcsrcvr_priv.h"
#include "pios_litewing_gcsrcvr.h"
#include "litewing_pilot_controller.h"
#include "litewing_pilot_wire.h"
#include "pios_litewing_pilot_mac.h"
#include <string.h>

static int64_t clock_us = 1000;
static GCSReceiverData object;
int64_t esp_timer_get_time(void) { return clock_us; }
UAVObjHandle GCSReceiverHandle(void) { return &object; }
int32_t UAVObjUnpack(UAVObjHandle obj, uint16_t instance, const uint8_t *data)
{
    assert(obj == &object && instance == 0);
    memcpy(&object, data, sizeof(object));
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
    struct lw_pilot_controller controller;
    lw_controller_init(&controller);
    struct lw_pilot_mac_key root, key;
    memset(root.bytes, 'r', 32);
    struct lw_wire_frame frame = {0};
    frame.kind = 1; frame.payload_len = 32;
    memset(frame.payload, 'h', 32);
    uint8_t wire[594], reply[594];
    size_t size, written;
    unsigned counter = 0;
    assert(lw_wire_encode(&frame,lw_pilot_mac,&root,wire,sizeof(wire),&size)==0);
    assert(lw_controller_receive(&controller,wire,size,root.bytes,clock_us,1,1,
        random_bytes,&counter,reply,sizeof(reply),&written)==LW_HANDSHAKE_REPLY);
    memset(&frame,0,sizeof(frame));
    frame.kind=3; frame.sequence=1;
    memcpy(frame.session,controller.session.session,16);
    memcpy(frame.challenge,controller.session.challenge,16);
    memcpy(key.bytes,controller.session.keys.c2b,32);
    assert(lw_wire_encode(&frame,lw_pilot_mac,&key,wire,sizeof(wire),&size)==0);
    clock_us=1100;
    if (!strcmp(argv[1],"busy")) {
        GCSReceiverData usb={.Channel={1500}};
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(uint8_t *)&usb,clock_us)==0);
    }
    int disarmed=strcmp(argv[1],"armed")!=0;
    int neutral=strcmp(argv[1],"not-neutral")!=0;
    enum lw_session_result result=lw_controller_receive(&controller,wire,size,root.bytes,
        clock_us,disarmed,neutral,random_bytes,&counter,reply,sizeof(reply),&written);
    if (!disarmed || !neutral || !strcmp(argv[1],"busy")) {
        assert(result!=LW_HANDSHAKE_REPLY && written==0 && !controller.owned);
        assert(controller.session.phase==LW_CLOSED);
        return 0;
    }
    assert(result==LW_HANDSHAKE_REPLY && written>0 && controller.owned);
    assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,0)==PIOS_RCVR_TIMEOUT);
    frame.kind=5; frame.sequence=2; frame.payload_len=16;
    for (unsigned i=0;i<8;++i) { frame.payload[2*i]=5; frame.payload[2*i+1]=220; }
    assert(lw_wire_encode(&frame,lw_pilot_mac,&key,wire,sizeof(wire),&size)==0);
    clock_us=2000;
    assert(lw_controller_receive(&controller,wire,size,root.bytes,clock_us,0,0,
        random_bytes,&counter,reply,sizeof(reply),&written)==LW_PILOT_CANDIDATE);
    assert(written==0 && pios_gcsrcvr_rcvr_driver.read(receiver_id,0)==1500);
    if (!strcmp(argv[1],"queued") || !strcmp(argv[1],"tick-queued") ||
        !strcmp(argv[1],"stale-queue") || !strcmp(argv[1],"future-receive") ||
        !strcmp(argv[1],"clock-rollback")) {
        clock_us=50000;
        if (!strcmp(argv[1],"tick-queued"))
            assert(lw_controller_tick(&controller,clock_us)==0);
        frame.sequence=3;
        assert(lw_wire_encode(&frame,lw_pilot_mac,&key,wire,sizeof(wire),&size)==0);
        assert(lw_controller_receive(&controller,wire,size,root.bytes,22000,0,0,
            random_bytes,&counter,reply,sizeof(reply),&written)==LW_PILOT_CANDIDATE);
        frame.sequence=4;
        assert(lw_wire_encode(&frame,lw_pilot_mac,&key,wire,sizeof(wire),&size)==0);
        clock_us=51000;
        if (!strcmp(argv[1],"stale-queue")) clock_us=76001;
        if (!strcmp(argv[1],"clock-rollback")) clock_us=49000;
        int64_t received=!strcmp(argv[1],"future-receive") ? 52000 : 23000;
        result=lw_controller_receive(&controller,wire,size,root.bytes,received,0,0,
            random_bytes,&counter,reply,sizeof(reply),&written);
        if (!strcmp(argv[1],"queued") || !strcmp(argv[1],"tick-queued")) {
            assert(result==LW_PILOT_CANDIDATE);
            assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,0)==1500);
        } else {
            assert(result!=LW_PILOT_CANDIDATE);
        }
        return 0;
    }
    if (!strcmp(argv[1],"publish")) return 0;
    if (!strcmp(argv[1],"stop")) {
        frame.kind=6; frame.sequence=3; frame.payload_len=0;
        assert(lw_wire_encode(&frame,lw_pilot_mac,&key,wire,sizeof(wire),&size)==0);
        clock_us=3000;
        assert(lw_controller_receive(&controller,wire,size,root.bytes,clock_us,0,0,
            random_bytes,&counter,reply,sizeof(reply),&written)==LW_RETIRED);
    } else if (!strcmp(argv[1],"timeout")) {
        clock_us=101000;
        assert(lw_controller_tick(&controller,clock_us)==-1);
    } else {
        assert(!strcmp(argv[1],"fault"));
        lw_controller_fault(&controller);
    }
    assert(controller.owned && controller.session.phase==LW_CLOSED);
    assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,0)==PIOS_RCVR_TIMEOUT);
    assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(uint8_t *)&object,clock_us)==-1);
    assert(lw_controller_release(&controller,0,1)==-1);
    assert(lw_controller_release(&controller,1,0)==-1);
    assert(controller.owned);
    assert(lw_controller_release(&controller,1,1)==0 && !controller.owned);
    clock_us++;
    assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(uint8_t *)&object,clock_us)==0);
    return 0;
}
