/* Actual adapted UAVTalk parser + actual target receiver, without hardware. */
#include "openpilot.h"
#include "pios_gcsrcvr_priv.h"
#include "uavtalk_priv.h"
#include <stdio.h>

static int64_t now_us=1000;
static int64_t connection_delay, lookup_delay;
static GCSReceiverData object;
static int locks[4], next_lock;
static uint32_t receiver_id;
static int unpack_result, unpack_calls;

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
    return id==UINT32_C(0xcc7e1470)?&object:NULL;
}
uint32_t UAVObjGetID(UAVObjHandle obj) { assert(obj==&object); return UINT32_C(0xcc7e1470); }
uint16_t UAVObjGetNumBytes(UAVObjHandle obj) { assert(obj==&object); return 16; }
uint16_t UAVObjGetNumInstances(UAVObjHandle obj) { assert(obj==&object); return 1; }
bool UAVObjIsSingleInstance(UAVObjHandle obj) { assert(obj==&object); return true; }
int32_t UAVObjPack(UAVObjHandle obj,uint16_t instance,uint8_t *out) {
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
static int32_t output(uint8_t *data,int32_t count) { (void)data; return count; }
static void expect(int32_t want) {
    const int32_t got=pios_gcsrcvr_rcvr_driver.read(receiver_id,0);
    if(got!=want) { fprintf(stderr,"at %lld wanted %d got %d\n",(long long)now_us,want,got); exit(1); }
}
int main(int argc,char **argv) {
    assert(argc==2);
    assert(PIOS_GCSRCVR_Init(&receiver_id)==0);
    UAVTalkConnection con=UAVTalkInitialize(output); assert(con);
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
