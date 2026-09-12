/* Parser platform/object boundaries for the real worker/store fixture. */
#include "openpilot.h"
int32_t LiteWingImuTimingPack(UAVObjHandle o,uint16_t i,uint8_t *d) {
    (void)o;(void)i;(void)d;return -1;
}
#include "pios_gcsrcvr_priv.h"
#include "uavtalk_priv.h"
#include <pthread.h>
#include <stdio.h>
int32_t LiteWingPwmObservationPack(UAVObjHandle obj,uint16_t instance,uint8_t *out) {
    (void)obj; (void)instance; (void)out; assert(false); return -1;
}
int32_t LiteWingImuHealthPack(UAVObjHandle obj,uint16_t instance,uint8_t *out) {
    (void)obj; (void)instance; (void)out; assert(false); return -1;
}
extern int64_t esp_timer_get_time(void);
static uint8_t incoming[163], emitted[46];
static size_t emitted_size;
static UAVTalkConnection connection;
static pthread_mutex_t parser_locks[4];
static unsigned lock_count;
void *xSemaphoreCreateRecursiveMutex(void) {
    assert(lock_count<4);
    pthread_mutexattr_t attr; assert(!pthread_mutexattr_init(&attr));
    assert(!pthread_mutexattr_settype(&attr,PTHREAD_MUTEX_RECURSIVE));
    pthread_mutex_t *m=&parser_locks[lock_count++];
    assert(!pthread_mutex_init(m,&attr)); pthread_mutexattr_destroy(&attr); return m;
}
int xSemaphoreTakeRecursive(void *m,uint32_t ticks) { (void)ticks; return !pthread_mutex_lock(m); }
int xSemaphoreGiveRecursive(void *m) { return !pthread_mutex_unlock(m); }
int xSemaphoreTake(void *m,uint32_t ticks) { (void)m; (void)ticks; return 0; }
int xSemaphoreGive(void *m) { (void)m; return 1; }
uint32_t xTaskGetTickCount(void) { return (uint32_t)(esp_timer_get_time()/1000); }
UAVObjHandle UAVObjGetByID(uint32_t id) { return id==0xcc7e1470 ? GCSReceiverHandle() : NULL; }
uint32_t UAVObjGetID(UAVObjHandle obj) { assert(obj==GCSReceiverHandle()); return 0xcc7e1470; }
uint16_t UAVObjGetNumBytes(UAVObjHandle obj) { assert(obj==GCSReceiverHandle()); return 16; }
uint16_t UAVObjGetNumInstances(UAVObjHandle obj) { (void)obj; return 1; }
bool UAVObjIsSingleInstance(UAVObjHandle obj) { (void)obj; return true; }
int32_t UAVObjPack(UAVObjHandle obj,uint16_t instance,uint8_t *out) {
    assert(obj==GCSReceiverHandle() && !instance); memcpy(out,obj,16); return 0;
}
uint8_t PIOS_CRC_updateByte(uint8_t crc,uint8_t value) {
    crc^=value;
    for(int i=0;i<8;++i) crc=(crc&128)?(uint8_t)((crc<<1)^7):(uint8_t)(crc<<1);
    return crc;
}
uint8_t PIOS_CRC_updateCRC(uint8_t crc,const uint8_t *data,int32_t size) {
    for(int32_t i=0;i<size;++i) crc=PIOS_CRC_updateByte(crc,data[i]);
    return crc;
}
static int32_t output(uint8_t *data,int32_t size) {
    assert(size>0 && emitted_size+(size_t)size<=sizeof(emitted));
    memcpy(emitted+emitted_size,data,(size_t)size); emitted_size+=(size_t)size; return size;
}
void host_read_frame(uint8_t *payload) {
    assert(fread(incoming,1,sizeof(incoming),stdin)==sizeof(incoming) && fgetc(stdin)==EOF);
    memcpy(payload,incoming+10,152);
}
void host_submit_frame(void) {
    connection=UAVTalkInitialize(output); assert(connection);
    for(size_t i=0;i<sizeof(incoming);++i) {
        assert(emitted_size==0);
        UAVTalkProcessInputStream(connection,incoming+i,1);
    }
    assert(emitted_size==11 && emitted[1]==0x23);
    for(size_t i=0;i<UAVTALK_MAX_PACKET_LENGTH;++i)
        assert(((UAVTalkConnectionData *)connection)->rxBuffer[i]==0);
}
void host_emit_status(void) {
    uint8_t query[11]={0x3c,0x21,10,0,0x48,0x50,0x57,0x4c,0,0,0};
    query[10]=PIOS_CRC_updateCRC(0,query,10);
    UAVTalkProcessInputStream(connection,query,sizeof(query));
    assert(emitted_size==sizeof(emitted));
    assert(fwrite(emitted,1,emitted_size,stdout)==emitted_size);
}
