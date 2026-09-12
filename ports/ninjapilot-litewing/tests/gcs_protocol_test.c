/* Actual adapted UAVTalk parser + actual target receiver, without hardware. */
#include "openpilot.h"
#include "pios_gcsrcvr_priv.h"
#include "pios_litewing_gcsrcvr.h"
#include "uavtalk_priv.h"
#include <stdio.h>
#include <math.h>
#include "litewing_battery_pack.h"
int32_t LiteWingPwmObservationPack(UAVObjHandle obj, uint16_t instance, uint8_t *data) {
    (void)obj; (void)instance; (void)data; return -1;
}
#include "litewing_wifi_config.h"
#include "pios_litewing_usb_maintenance.h"

int32_t LiteWingImuHealthPack(UAVObjHandle obj,uint16_t instance,uint8_t *out) {
    (void)obj; (void)instance; (void)out; assert(false); return -1;
}

static int64_t now_us=1000;
static int64_t connection_delay, lookup_delay;
static GCSReceiverData object;
static uint8_t battery[30];
static uint8_t transmitted[64];
static int transmitted_count;
static int locks[4], next_lock;
static uint32_t receiver_id;
static int unpack_result, unpack_calls;
static int maintenance_calls, maintenance_queued, collision;
static int output_failure;
static uint8_t queued[152];
int lw_usb_maintenance_submit(const uint8_t *data,size_t size) {
    ++maintenance_calls;
    struct lw_wifi_config decoded;
    if(size!=152 || lw_wifi_config_decode(data+16,size-16,&decoded)) return -1;
    lw_wifi_config_clear(&decoded);
    if(maintenance_queued) return -1;
    memcpy(queued,data,152); maintenance_queued=1; return 0;
}
int lw_usb_maintenance_status(uint8_t *out,size_t size) {
    assert(size>=24); memset(out,0,24); out[0]=1; out[1]=2;
    memset(out+4,'t',16); return 24;
}

int64_t esp_timer_get_time(void) { return now_us; }
uint32_t xTaskGetTickCount(void) { return (uint32_t)(now_us/1000); }
void *xSemaphoreCreateRecursiveMutex(void) { assert(next_lock<4); return &locks[next_lock++]; }
int xSemaphoreTakeRecursive(void *lock,uint32_t wait) {
    (void)wait;
    if(lock==&locks[0]) { now_us+=connection_delay; connection_delay=0; }
    return pdTRUE;
}
int xSemaphoreGiveRecursive(void *lock) { (void)lock; return pdTRUE; }
int xSemaphoreTake(void *lock,uint32_t wait) { (void)lock; (void)wait; return pdFALSE; }
int xSemaphoreGive(void *lock) { (void)lock; return pdTRUE; }
UAVObjHandle GCSReceiverHandle(void) { return &object; }
UAVObjHandle UAVObjGetByID(uint32_t id) {
    now_us+=lookup_delay; lookup_delay=0;
    if(id==UINT32_C(0x26962352)) return battery;
    if((collision==1 && id==UINT32_C(0x4c575046)) ||
       (collision==2 && id==UINT32_C(0x4c575048))) return &object;
    return id==UINT32_C(0xcc7e1470)?&object:NULL;
}
uint32_t UAVObjGetID(UAVObjHandle obj) { return obj==battery?UINT32_C(0x26962352):UINT32_C(0xcc7e1470); }
uint16_t UAVObjGetNumBytes(UAVObjHandle obj) { return obj==battery?30:collision==1?152:16; }
uint16_t UAVObjGetNumInstances(UAVObjHandle obj) { (void)obj; return 1; }
bool UAVObjIsSingleInstance(UAVObjHandle obj) { (void)obj; return true; }
int32_t UAVObjPack(UAVObjHandle obj,uint16_t instance,uint8_t *out) {
    if(obj==battery) { assert(instance==0); memcpy(out,battery,30); return 0; }
    assert(obj==&object && instance==0); memcpy(out,&object,16); return 0;
}
int32_t UAVObjUnpack(UAVObjHandle obj,uint16_t instance,const uint8_t *data) {
    ++unpack_calls;
    if(unpack_result) return unpack_result;
    if(obj!=&object || instance) return -1;
    memcpy(&object,data,16); return 0;
}
/* Independent bitwise CRC implementation, not the production framing helper. */
uint8_t PIOS_CRC_updateByte(uint8_t crc,uint8_t value) {
    crc^=value;
    for(int bit=0;bit<8;++bit) crc=(crc&128)?(uint8_t)((crc<<1)^7):(uint8_t)(crc<<1);
    return crc;
}
uint8_t PIOS_CRC_updateCRC(uint8_t crc,const uint8_t *bytes,int32_t count) {
    for(int i=0;i<count;++i) crc=PIOS_CRC_updateByte(crc,bytes[i]);
    return crc;
}
static int32_t output(uint8_t *data,int32_t count) {
    assert(count<=64); memcpy(transmitted,data,count); transmitted_count=count;
    if(output_failure) { int rc=output_failure; output_failure=0; return rc; }
    return count;
}
static void expect(int32_t want) {
    const int32_t got=pios_gcsrcvr_rcvr_driver.read(receiver_id,0);
    if(got!=want) { fprintf(stderr,"at %lld wanted %d got %d\n",(long long)now_us,want,got); exit(1); }
}
static void provisioning(UAVTalkConnection con,const char *name) {
    uint8_t packet[164]={0x3c,0x22,162,0,0x46,0x50,0x57,0x4c,0,0};
    memset(packet+10,'t',16); memcpy(packet+26,"LWCF",4);
    packet[30]=1; packet[31]=1; packet[32]=16;
    memset(packet+34,'k',32); packet[66]='x'; memset(packet+98,'p',16);
    unsigned length=163;
    if(strstr(name,"-status")) {
        packet[1]=0x21; packet[2]=10; packet[4]=0x48; length=11;
    }
    if(!strcmp(name,"provision-instance")) packet[8]=1;
    if(!strcmp(name,"provision-type")) packet[1]=0x20;
    if(!strcmp(name,"provision-invalid")) packet[33]=1;
    if(!strcmp(name,"provision-length")) { --length; --packet[2]; }
    if(strstr(name,"collision1")) collision=1;
    if(strstr(name,"collision2")) collision=2;
    if(!strcmp(name,"provision-write-fail")) output_failure=-1;
    if(!strcmp(name,"provision-write-short")) output_failure=5;
    packet[length-1]=PIOS_CRC_updateCRC(0,packet,length-1);
    if(!strcmp(name,"provision-crc")) packet[length-1]^=1;
    if(!strcmp(name,"provision-host")) {
        assert(fread(packet,1,163,stdin)==163 && fgetc(stdin)==EOF);
    }
    if(!strncmp(name,"provision-expire",16)) {
        if(!strcmp(name,"provision-expire-complete") || !strcmp(name,"provision-expire-lookup")) {
            uint8_t position=0;
            assert(UAVTalkProcessInputStreamQuiet(con,packet,163,&position)==UAVTALK_STATE_COMPLETE);
            if(!strcmp(name,"provision-expire-lookup")) lookup_delay=2000000;
            else now_us+=2000000;
            assert(UAVTalkReceiveObject(con)==-1);
        } else {
            UAVTalkProcessInputStream(con,packet,100);
            assert(!maintenance_calls && !transmitted_count);
            if(!strcmp(name,"provision-expire-drip") || !strcmp(name,"provision-expire-rollback")) {
                now_us+=1000000;
                UAVTalkProcessInputStream(con,packet+100,1);
            }
            now_us=!strcmp(name,"provision-expire-rollback") ? 500000 : 2001000;
            UAVTalkProcessInputStream(con,NULL,0);
        }
        assert(!maintenance_calls && !transmitted_count);
        for(unsigned i=0;i<UAVTALK_MAX_PACKET_LENGTH;++i)
            assert(((UAVTalkConnectionData *)con)->rxBuffer[i]==0);
        /* Cleanup must permit a fresh frame, not a stale resumed payload. */
        UAVTalkProcessInputStream(con,packet,163);
        assert(maintenance_calls==1 && maintenance_queued);
        return;
    }
    if(!strcmp(name,"provision-relay")) {
        uint8_t position=0;
        assert(UAVTalkProcessInputStreamQuiet(con,packet,length,&position)==UAVTALK_STATE_COMPLETE);
        assert(UAVTalkRelayPacket(con,con)==-1);
        assert(!maintenance_calls && !transmitted_count); return;
    }
    unsigned split=1;
    if(!strncmp(name,"provision-split-",16)) split=(unsigned)strtoul(name+16,NULL,10);
    assert(split>0 && split<length);
    UAVTalkProcessInputStream(con,packet,split);
    assert(!maintenance_calls && !transmitted_count);
    UAVTalkProcessInputStream(con,packet+split,length-split);
    assert(!unpack_calls);
    if(!strcmp(name,"provision-status")) {
        assert(!maintenance_calls && transmitted_count==35);
        const uint8_t header[10]={0x3c,0x20,34,0,0x48,0x50,0x57,0x4c,0,0};
        assert(!memcmp(transmitted,header,10));
        assert(transmitted[10]==1 && transmitted[11]==2 && transmitted[12]==0);
        for(unsigned i=14;i<30;++i) assert(transmitted[i]=='t');
        assert(transmitted[34]==PIOS_CRC_updateCRC(0,transmitted,34));
        for(int i=0;i<transmitted_count;++i) printf("%02x",transmitted[i]);
        puts("");
    } else if(!strncmp(name,"provision-split-",16) || !strcmp(name,"provision-host") ||
              !strncmp(name,"provision-write-",16)) {
        assert(maintenance_calls==1 && maintenance_queued);
        assert(!memcmp(queued,packet+10,152));
        const uint8_t ack[11]={0x3c,0x23,10,0,0x46,0x50,0x57,0x4c,0,0,0xff};
        assert(transmitted_count==11 && !memcmp(transmitted,ack,11));
        for(unsigned i=0;i<UAVTALK_MAX_PACKET_LENGTH;++i)
            assert(((UAVTalkConnectionData *)con)->rxBuffer[i]==0);
        if(!strcmp(name,"provision-host")) {
            for(int i=0;i<transmitted_count;++i) printf("%02x",transmitted[i]);
            puts("");
        }
        /* ACK loss/replay cannot cause a second queued transaction. */
        UAVTalkProcessInputStream(con,packet,length);
        assert(maintenance_calls==2 && transmitted_count==11 && transmitted[1]==0x24);
        if(!strncmp(name,"provision-write-",16)) {
            /* A failed ACK must not roll back acceptance or poison the parser. */
            assert(((UAVTalkConnectionData *)con)->stats.txErrors==1);
            assert(maintenance_queued && !memcmp(queued,packet+10,152));
            uint8_t request[11]={0x3c,0x21,10,0,0x48,0x50,0x57,0x4c,0,0,0};
            request[10]=PIOS_CRC_updateCRC(0,request,10);
            UAVTalkProcessInputStream(con,request,11);
            assert(transmitted_count==35 && transmitted[1]==0x20);
            request[4]=0x70; request[5]=0x14; request[6]=0x7e; request[7]=0xcc;
            request[10]=PIOS_CRC_updateCRC(0,request,10);
            UAVTalkProcessInputStream(con,request,11);
            assert(transmitted_count==27 && transmitted[1]==0x20 && !unpack_calls);
        }
    } else {
        assert(!maintenance_queued);
        if(strcmp(name,"provision-invalid")) assert(!maintenance_calls);
        if(transmitted_count) assert(transmitted_count==11 && transmitted[1]==0x24);
    }
    UAVTalkConnectionData *connection=(UAVTalkConnectionData *)con;
    for(unsigned i=0;i<UAVTALK_MAX_PACKET_LENGTH;++i) assert(connection->rxBuffer[i]==0);
}
int main(int argc,char **argv) {
    assert(argc==2);
    assert(PIOS_GCSRCVR_Init(&receiver_id)==0);
    UAVTalkConnection con=UAVTalkInitialize(output); assert(con);
    if(!strncmp(argv[1],"provision-",10)) { provisioning(con,argv[1]); return 0; }
    if(!strncmp(argv[1],"request-",8)) {
        if(!strcmp(argv[1],"request-wireless-owner")) {
            const uint8_t session[16]={1};
            assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(session,1)==0);
        }
        float voltage=3.9f; memcpy(battery,&voltage,4);
        struct litewing_battery_sample sample={.valid=true,.millivolts=3900,.captured_us=now_us};
        if(!strcmp(argv[1],"request-invalid")) sample.valid=false;
        if(!strcmp(argv[1],"request-future")) sample.captured_us++;
        if(strcmp(argv[1],"request-uninitialized")) LiteWingBatteryStoreSample(&sample);
        bool other=!strcmp(argv[1],"request-other");
        if(!strcmp(argv[1],"request-stale")) now_us+=500001;
        if(!strcmp(argv[1],"request-boundary")) now_us+=500000;
        uint8_t request[11]={0x3c,0x21,10,0,0x52,0x23,0x96,0x26,0,0,0};
        if(other) { uint32_t id=0xcc7e1470; memcpy(request+4,&id,4); }
        request[10]=PIOS_CRC_updateCRC(0,request,10);
        uint8_t consumed=0;
        assert(UAVTalkProcessInputStreamQuiet(con,request,11,&consumed)==UAVTALK_STATE_COMPLETE);
        assert(UAVTalkReceiveObject(con)==0);
        assert(unpack_calls==0);
        assert(transmitted_count==(other?27:41));
        if(other) assert(!memcmp(transmitted+10,&object,16));
        else {
            memcpy(&voltage,transmitted+10,4);
            if(!strcmp(argv[1],"request-stale") || !strcmp(argv[1],"request-invalid") ||
               !strcmp(argv[1],"request-future") || !strcmp(argv[1],"request-uninitialized")) assert(isnan(voltage));
            else assert(fabsf(voltage-3.9f)<0.0001f);
            for(int field=1;field<7;field++) {
                float unavailable; memcpy(&unavailable,transmitted+10+field*4,4);
                assert(isnan(unavailable));
            }
            assert(transmitted[38]==1 && transmitted[39]==0);
            assert(transmitted[40]==PIOS_CRC_updateCRC(0,transmitted,40));
        }
        return 0;
    }
    /* Literal zero-instance, eight-channel object; channel zero is 1500. */
    uint8_t frame[27]={0x3c,0x20,26,0,0x70,0x14,0x7e,0xcc,0,0,
                       0xdc,5,0xdc,5,0xdc,5,0xdc,5,0xdc,5,0xdc,5,0xdc,5,0xdc,5,0};
    if(!strcmp(argv[1],"bad-length")) frame[2]=25;
    if(!strcmp(argv[1],"acked")) frame[1]=0x22;
    frame[26]=PIOS_CRC_updateCRC(0,frame,26);
    if(!strcmp(argv[1],"bad-crc")) frame[26]^=1;
    uint8_t pos=0;
    UAVTalkRxState state=UAVTalkProcessInputStreamQuiet(con,frame,sizeof(frame),&pos);
    if(!strcmp(argv[1],"bad-crc") || !strcmp(argv[1],"bad-length")) {
        assert(state==UAVTALK_STATE_ERROR && unpack_calls==0);
        expect(PIOS_RCVR_TIMEOUT); return 0;
    }
    assert(state==UAVTALK_STATE_COMPLETE && pos==27);
    if(!strcmp(argv[1],"connection-lock-delay")) connection_delay=150000;
    if(!strcmp(argv[1],"lookup-lock-delay")) lookup_delay=150000;
    if(!strcmp(argv[1],"between-parse-and-receive")) now_us+=150000;
    if(!strcmp(argv[1],"failed-unpack")) unpack_result=-7;
    int32_t rc=UAVTalkReceiveObject(con);
    if(!strcmp(argv[1],"failed-unpack")) {
        assert(rc==-1); expect(PIOS_RCVR_TIMEOUT); return 0;
    }
    assert(rc==0 && unpack_calls==1);
    if(strstr(argv[1],"delay") || !strcmp(argv[1],"between-parse-and-receive")) {
        expect(PIOS_RCVR_TIMEOUT);
    } else {
        expect(1500);
        now_us=101000; expect(PIOS_RCVR_TIMEOUT);
        /* Redelivery of the same parsed packet must not renew its age. */
        assert(UAVTalkReceiveObject(con)==0); expect(PIOS_RCVR_TIMEOUT);
    }
    return 0;
}
