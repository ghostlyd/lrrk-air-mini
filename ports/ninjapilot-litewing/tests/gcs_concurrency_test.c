#include "uavobjectmanager.h"
#include "pios_gcsrcvr_priv.h"
#include "pios_litewing_gcsrcvr.h"
#include <stdatomic.h>
#include <pthread.h>

static _Atomic int64_t now_us=1000;
static int object;
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition=PTHREAD_COND_INITIALIZER;
static bool old_waiting, release_old;
static uint32_t receiver_id;
int64_t esp_timer_get_time(void) { return atomic_load(&now_us); }
UAVObjHandle GCSReceiverHandle(void) { return &object; }
int32_t UAVObjUnpack(UAVObjHandle obj,uint16_t instance,const uint8_t *data) {
    assert(obj==&object && instance==0);
    GCSReceiverData packet;
    __builtin_memcpy(&packet,data,sizeof(packet));
    if(packet.Channel[0]==1500) {
        pthread_mutex_lock(&gate);
        old_waiting=true;
        pthread_cond_broadcast(&condition);
        while(!release_old) pthread_cond_wait(&condition,&gate);
        pthread_mutex_unlock(&gate);
    }
    return 0;
}
static void *old_writer(void *unused) {
    (void)unused;
    GCSReceiverData packet={.Channel={1500,1500,1500,1500,1500,1500,1500,1500}};
    assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(const uint8_t *)&packet,1000)==0);
    return NULL;
}
int main(void) {
    assert(PIOS_GCSRCVR_Init(&receiver_id)==0);
    pthread_t writer;
    assert(pthread_create(&writer,NULL,old_writer,NULL)==0);
    pthread_mutex_lock(&gate);
    while(!old_waiting) pthread_cond_wait(&condition,&gate);
    pthread_mutex_unlock(&gate);
    /* A different task is inside unpack; reads must not expose partial input. */
    for(int i=0;i<8;++i) assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,i)==PIOS_RCVR_TIMEOUT);
    atomic_store(&now_us,2000);
    GCSReceiverData newer={.Channel={1700,1701,1702,1703,1704,1705,1706,1707}};
    assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(const uint8_t *)&newer,2000)==0);
    for(int i=0;i<8;++i) assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,i)==1700+i);
    atomic_store(&now_us,102000);
    for(int i=0;i<8;++i) assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,i)==PIOS_RCVR_TIMEOUT);
    pthread_mutex_lock(&gate);
    release_old=true;
    pthread_cond_broadcast(&condition);
    pthread_mutex_unlock(&gate);
    assert(pthread_join(writer,NULL)==0);
    /* Delayed older completion must not resurrect the expired newer input. */
    for(int i=0;i<8;++i) assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,i)==PIOS_RCVR_TIMEOUT);
    atomic_store(&now_us,103000);
    assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(const uint8_t *)&newer,103000)==0);
    for(int i=0;i<8;++i) assert(pios_gcsrcvr_rcvr_driver.read(receiver_id,i)==1700+i);
    return 0;
}
