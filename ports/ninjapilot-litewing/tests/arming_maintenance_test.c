#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <pthread.h>
#include "litewing_arming_maintenance.h"
typedef void *UAVObjHandle;
typedef struct { uint8_t Armed, remainder[7]; } FlightStatusData;
#define FLIGHTSTATUS_ARMED_DISARMED 0
struct UAVOBase { int unused; };
struct UAVOMeta { uint8_t bytes[8]; };
struct UAVOData { size_t instance_size; uint8_t bytes[8]; };
typedef struct UAVOData *InstanceHandle;
static struct UAVOData flight={.instance_size=8}, other={.instance_size=8};
#ifdef IMU_ACCESS_TEST
static struct UAVOData imu={.instance_size=8};
static struct UAVOMeta imu_meta;
static uint32_t diagnostic_id = 0xDA60A0C6;
#endif
uint32_t UAVObjGetID(UAVObjHandle h) {
#ifdef IMU_ACCESS_TEST
    if(h==&imu) return diagnostic_id;
    if(h==&imu_meta) return diagnostic_id+1;
#endif
    (void)h; return 0;
}
static pthread_mutex_t storage;
static pthread_mutex_t *mutex=&storage;
#define portMAX_DELAY UINT32_MAX
#define pdTRUE 1
#define PIOS_Assert assert
#define MetaNumBytes 8
#define EV_UPDATED 1
#define EV_UNPACKED 2
static int xSemaphoreTakeRecursive(pthread_mutex_t *m,uint32_t wait) {
    return (wait ? pthread_mutex_lock(m) : pthread_mutex_trylock(m))==0;
}
static void xSemaphoreGiveRecursive(pthread_mutex_t *m) { assert(!pthread_mutex_unlock(m)); }
static UAVObjHandle FlightStatusHandle(void) { return &flight; }
static int FlightStatusGet(FlightStatusData *out) {
    assert(xSemaphoreTakeRecursive(mutex,portMAX_DELAY));
    memcpy(out,flight.bytes,8); xSemaphoreGiveRecursive(mutex); return 0;
}
static int UAVObjIsMetaobject(UAVObjHandle h) { (void)h; return 0; }
static int UAVObjReadOnly(UAVObjHandle h) { (void)h; return 0; }
static uint8_t *MetaDataPtr(struct UAVOMeta *obj) { return obj->bytes; }
static InstanceHandle getInstance(struct UAVOData *obj,uint16_t id) { return id ? NULL : obj; }
static InstanceHandle createInstance(struct UAVOData *obj,uint16_t id) { return getInstance(obj,id); }
static uint8_t *InstanceData(InstanceHandle h) { return h->bytes; }
static unsigned events;
static void sendEvent(struct UAVOBase *obj,uint16_t id,int event) {
    (void)obj; (void)id; (void)event; ++events;
}
#include "litewing_arming_maintenance.inc"
#include "writes.inc"
static pthread_mutex_t coordination=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t signal=PTHREAD_COND_INITIALIZER;
static int ready, proceed;
static void *paused_arm(void *unused) {
    (void)unused;
    FlightStatusData cached; assert(!FlightStatusGet(&cached)); cached.Armed=2;
    pthread_mutex_lock(&coordination); ready=1; pthread_cond_broadcast(&signal);
    while (!proceed) pthread_cond_wait(&signal,&coordination);
    pthread_mutex_unlock(&coordination);
    assert(UAVObjSetInstanceData(&flight,0,&cached)==-1);
    return NULL;
}
static void *busy_begin(void *unused) {
    (void)unused; uint64_t token=99;
    assert(lw_arming_maintenance_begin(&token)==-1 && token==0); return NULL;
}
int main(void) {
    pthread_mutexattr_t attr; pthread_mutexattr_init(&attr);
    pthread_mutexattr_settype(&attr,PTHREAD_MUTEX_RECURSIVE);
    pthread_mutex_init(mutex,&attr); pthread_mutexattr_destroy(&attr);
#ifdef IMU_ACCESS_TEST
    uint8_t forged[8]={1};
    const uint32_t diagnostic_ids[]={0xDA60A0C6,0xA6453F6E,0xE7AF695A,0x5AF673A8};
    for (unsigned i=0;i<sizeof diagnostic_ids/sizeof diagnostic_ids[0];++i) {
        diagnostic_id=diagnostic_ids[i];
        assert(UAVObjUnpack(&imu,0,forged)==-1);
        assert(UAVObjUnpack(&imu_meta,0,forged)==-1);
    }
    assert(imu.bytes[0]==0 && imu_meta.bytes[0]==0 && events==0);
    assert(UAVObjSetInstanceData(&imu,0,forged)==0 && imu.bytes[0]==1);
    events=0;
#endif
    pthread_t thread;
    /* Bounded acquisition must not wait behind another task's object lock. */
    pthread_mutex_lock(mutex); pthread_create(&thread,NULL,busy_begin,NULL);
    pthread_join(thread,NULL); pthread_mutex_unlock(mutex);
    pthread_create(&thread,NULL,paused_arm,NULL);
    pthread_mutex_lock(&coordination);
    while (!ready) pthread_cond_wait(&signal,&coordination);
    uint64_t token=0, other_token=99;
    assert(lw_arming_maintenance_begin(&token)==0 && token);
    assert(lw_arming_maintenance_begin(&other_token)==-1 && !other_token);
    proceed=1; pthread_cond_broadcast(&signal); pthread_mutex_unlock(&coordination);
    pthread_join(thread,NULL);
    assert(flight.bytes[0]==0 && events==0 && lw_arming_maintenance_held(token)==1);
    uint8_t armed[8]={2}, disarmed[8]={0};
    assert(UAVObjUnpack(&flight,0,armed)==-1);
    assert(UAVObjSetInstanceDataField(&flight,0,armed,0,1)==-1);
    assert(UAVObjSetInstanceData(&other,0,armed)==0 && other.bytes[0]==2);
    assert(UAVObjSetInstanceDataField(&flight,0,armed,1,1)==0 && flight.bytes[1]==2);
    assert(UAVObjSetInstanceData(&flight,0,disarmed)==0);
    assert(lw_arming_maintenance_end(token+1)==-1);
    assert(lw_arming_maintenance_held(token)==1);
    assert(lw_arming_maintenance_end(token)==0);
    assert(!lw_arming_maintenance_held(token));
    assert(UAVObjSetInstanceData(&flight,0,armed)==0 && flight.bytes[0]==2);
    assert(lw_arming_maintenance_begin(&other_token)==-1 && !other_token);
    assert(UAVObjSetInstanceData(&flight,0,disarmed)==0);
    assert(lw_arming_maintenance_begin(&other_token)==0 && other_token!=token);
    assert(lw_arming_maintenance_end(token)==-1);
    assert(lw_arming_maintenance_end(other_token)==0);
    return 0;
}
