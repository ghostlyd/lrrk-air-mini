/* Real receiver adapter; only clock and UAVObject storage are controlled. */
#include "uavobjectmanager.h"
#include "pios_gcsrcvr_priv.h"
#include "pios_litewing_gcsrcvr.h"
#include <stdio.h>
#include <string.h>
#include <limits.h>

static int64_t now_us = 1000;
static GCSReceiverData object;
static UAVObjEventCallback callback;
static int unpack_result;
static int64_t unpack_delay;
static int64_t pre_unpack_delay;
static uint32_t receiver_id = 1234;
static int other_object;
static bool inject_newer;
static bool inject_claim;
static const uint8_t wifi_session[16] = {1};

int64_t esp_timer_get_time(void) { return now_us; }
UAVObjHandle GCSReceiverHandle(void) { return &object; }
int32_t GCSReceiverGet(GCSReceiverData *out) { *out = object; return 0; }
int32_t GCSReceiverConnectCallback(UAVObjEventCallback cb) { callback = cb; return 0; }
static void event(UAVObjEventType kind) {
    UAVObjEvent ev = {.obj=&object, .instId=0, .event=kind, .lowPriority=false};
    if (callback) callback(&ev);
}
int32_t UAVObjUnpack(UAVObjHandle obj, uint16_t instance, const uint8_t *data) {
    now_us += unpack_delay;
    if (unpack_result) return unpack_result;
    if (inject_claim) {
        inject_claim = false;
        assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(wifi_session, 1) == 0);
    }
    if (obj == &object && instance == 0) {
        memcpy(&object, data, sizeof(object));
        event(EV_UNPACKED);
        if (inject_newer) {
            inject_newer = false;
            now_us += 10;
            GCSReceiverData newer = {.Channel={1700,1700,1700,1700,1700,1700,1700,1700}};
            assert(PIOS_LiteWing_GCSReceiver_Unpack(&object, 0, (const uint8_t *)&newer, now_us) == 0);
        }
    }
    return 0;
}
#ifdef LRRK_TEST_UPSTREAM
int32_t PIOS_LiteWing_GCSReceiver_Unpack(UAVObjHandle obj, uint16_t instance, const uint8_t *data, int64_t received_time) {
    (void)received_time;
    return UAVObjUnpack(obj, instance, data);
}
#endif
static void input(uint16_t value) {
    GCSReceiverData frame;
    for (int i=0;i<8;++i) frame.Channel[i]=value+i;
    const int64_t completed_us=now_us;
    now_us+=pre_unpack_delay;
    assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(const uint8_t *)&frame,completed_us)==unpack_result);
}
static int32_t read_channel(int index) { return pios_gcsrcvr_rcvr_driver.read(receiver_id,index); }
static void expect(int index, int32_t want) {
    int32_t got=read_channel(index);
    /* Both signed timeout and the existing uint16 timeout cast are accepted. */
    if ((uint16_t)got != (uint16_t)want) {
        fprintf(stderr,"channel %d at %lld us: wanted %d got %d\n",index,(long long)now_us,want,got);
        exit(1);
    }
}
int main(int argc,char **argv) {
    assert(argc==2);
    assert(PIOS_GCSRCVR_Init(&receiver_id)==0);
    const char *name=argv[1];
    if (!strcmp(name,"startup")) {
        for(int i=0;i<8;++i) expect(i,PIOS_RCVR_TIMEOUT);
        now_us=INT64_C(900000000000); expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"cached-expires")) {
        input(1500);
        for(int i=0;i<8;++i) expect(i,1500+i);
        now_us=100999; expect(0,1500);
        now_us=101000; expect(0,PIOS_RCVR_TIMEOUT);
        now_us=900000; expect(7,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"reads-do-not-renew")) {
        input(1500);
        for(int i=1;i<100;++i) { now_us=1000+i*1000; expect(0,1500); }
        now_us=101000; expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"non-input-events")) {
        input(1500); now_us=99000;
        event(EV_UPDATED); event(EV_UPDATED_PERIODIC); event(EV_UPDATED_MANUAL);
        event(EV_LOGGING_MANUAL); event(EV_LOGGING_PERIODIC); event(EV_UPDATE_REQ);
        now_us=101000; expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"delayed-unpack")) {
        unpack_delay=100000; input(1500); expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"pre-wrapper-delay")) {
        pre_unpack_delay=150000; input(1500); expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"reconnect")) {
        input(1500); now_us=101000; expect(0,PIOS_RCVR_TIMEOUT);
        now_us=200000; input(1600); expect(0,1600);
        now_us=299999; expect(7,1607);
        now_us=300000; expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"same-values-new-packet")) {
        input(1500); now_us=90000; input(1500);
        now_us=189999; expect(0,1500);
        now_us=190000; expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"clock-32bit-boundaries")) {
        now_us=INT64_C(4294967290); input(1500);
        now_us=INT64_C(4295067289); expect(0,1500);
        now_us=INT64_C(4295067290); expect(0,PIOS_RCVR_TIMEOUT);
        now_us=INT64_C(4294967295000); input(1600);
        now_us=INT64_C(4294967395000); expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"clock-backwards")) {
        input(1500); now_us=999; expect(0,PIOS_RCVR_TIMEOUT);
        now_us=500; input(1700); expect(0,PIOS_RCVR_TIMEOUT);
        now_us=1001; expect(0,PIOS_RCVR_TIMEOUT);
        now_us=2000; input(1600); expect(0,1600);
    } else if (!strcmp(name,"failed-unpack")) {
        input(1500); now_us=99000; unpack_result=-7; input(1700);
        expect(0,1500); now_us=101000; expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"unrelated-object-instance")) {
        input(1500); now_us=99000;
        GCSReceiverData frame={.Channel={1700}};
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&other_object,0,(const uint8_t *)&frame,now_us)==0);
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,1,(const uint8_t *)&frame,now_us)==0);
        expect(0,1500); now_us=101000; expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"out-of-order-completion")) {
        inject_newer=true; input(1500); expect(0,1700);
        now_us=101010; expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"wireless-excludes-usb")) {
        assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(wifi_session, 0) == -1);
        assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(wifi_session, 1) == 0);
        GCSReceiverData frame={.Channel={1500}};
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(const uint8_t *)&frame,now_us)==-1);
        expect(0,PIOS_RCVR_TIMEOUT);
        assert(PIOS_LiteWing_GCSReceiver_ReleaseWireless(wifi_session, 0)==-1);
        uint8_t wrong[16]={2};
        assert(PIOS_LiteWing_GCSReceiver_ReleaseWireless(wrong, 1)==-1);
        assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(wrong, 1)==-1);
        now_us=2000;
        assert(PIOS_LiteWing_GCSReceiver_ReleaseWireless(wifi_session, 1)==0);
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(const uint8_t *)&frame,1500)==-1);
        now_us=3000; input(1600); expect(0,1600);
    } else if (!strcmp(name,"wireless-cannot-steal-fresh-usb")) {
        input(1500);
        assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(wifi_session, 1)==-1);
        expect(0,1500);
        now_us=101000;
        assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(wifi_session, 1)==0);
        expect(0,PIOS_RCVR_TIMEOUT);
    } else if (!strcmp(name,"ownership-change-during-unpack")) {
        inject_claim=true;
        input(1500);
        expect(0,PIOS_RCVR_TIMEOUT);
        now_us=2000;
        assert(PIOS_LiteWing_GCSReceiver_ReleaseWireless(wifi_session, 1)==0);
        expect(0,PIOS_RCVR_TIMEOUT);
        now_us=3000; input(1600); expect(0,1600);
    } else if (!strcmp(name,"handles-channels")) {
        assert(receiver_id != 0); expect(8,PIOS_RCVR_INVALID);
        assert(pios_gcsrcvr_rcvr_driver.read(0,0)==PIOS_RCVR_NODRIVER);
        assert(PIOS_GCSRCVR_Init(NULL)!=0);
        uint32_t duplicate=55; assert(PIOS_GCSRCVR_Init(&duplicate)!=0 && duplicate==0);
    } else { fprintf(stderr,"unknown case\n"); return 2; }
    return 0;
}
