#include "imu_publication_sdk.h"
#if CONFIG_LRRK_ATTITUDE_TRACE
int32_t LiteWingAttitudeTracePack(UAVObjHandle o,uint16_t i,uint8_t *d) {
 (void)o;(void)i;(void)d;return -1;
}
#endif
int32_t LiteWingPwmObservationPack(UAVObjHandle obj, uint16_t instance, uint8_t *data) {
    (void)obj; (void)instance; (void)data; return -1;
}
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include <stdatomic.h>
#include "../target/pios_litewing_mpu6050.c"
#include "../target/litewing_imu_health_module.c"
#include "../target/litewing_battery_pack.c"
static int64_t now=1000000;
static unsigned motor_writes, publications, creates;
static bool fail_read, reset_in_read;
static bool missed_notification;
static int64_t transfer_delay_us;
static uint8_t registers[128];
static int config_fault_reg=-1;
static bool config_read_failure;
static unsigned config_fault_bit;
static int64_t queue_delay_us;
static unsigned queue_item_size;
static uint8_t queue_copy[128];
static bool complete_reset_in_read;
static uint64_t pending_reset_generation;
static unsigned identity_reads, shutdown_on_identity_read;
static LiteWingIMUHealthData cached;
static uint8_t identity=0x68;
static const char *scenario;
static jmp_buf stopped;
static bool run_sensor;
static void (*worker)(void *);
static unsigned steps;
static bool is(const char *s) { return strcmp(scenario,s)==0; }
int64_t esp_timer_get_time(void) { return now; }
void PIOS_LiteWing_BrushedPWM_SetImuHealthy(bool h) { (void)h; motor_writes++; }
int PIOS_I2C_Transfer(uint32_t id,const struct pios_i2c_txn *t,unsigned n) {
 (void)id;
 assert(pthread_mutex_trylock(&observation_lock)==0); pthread_mutex_unlock(&observation_lock);
 if(n==2) {
   if(t[0].buf[0]==0x75) {
     if(++identity_reads==shutdown_on_identity_read) PIOS_LiteWing_MPU6050_Shutdown();
     t[1].buf[0]=identity; return 0;
   }
   if(t[0].buf[0]!=0x3b) {
     unsigned reg=t[0].buf[0];assert(t[1].len==1 && reg<128);
     if((int)reg==config_fault_reg && config_read_failure)return -1;
     t[1].buf[0]=registers[reg];
     if(is("reserved")) {
       const uint8_t masks[128]={[0x19]=0xff,[0x1a]=0x3f,[0x1b]=0xf8,
         [0x1c]=0xf8,[0x37]=0xfe,[0x38]=0x19,[0x6b]=0xef};
       t[1].buf[0]|=(uint8_t)~masks[reg];
     }
     if((int)reg==config_fault_reg)t[1].buf[0]^=config_fault_bit?config_fault_bit:
         (reg==0x1b || reg==0x1c)?8:reg==0x37?2:1;
     return 0;
   }
   if(reset_in_read) { reset_in_read=false; PIOS_LiteWing_MPU6050_Shutdown(); }
   if(complete_reset_in_read) {
     complete_reset_in_read=false;
     /* Resume the final validation of a reset that invalidated observation
      * before this acquisition started, without changing its generation. */
     assert(record_identity(identity,pending_reset_generation));
   }
   memset(t[1].buf,0,t[1].len);
   now+=transfer_delay_us;
   if(is("raw-provenance")) {
     for(unsigned i=0;i<t[1].len;i++)t[1].buf[i]=(uint8_t)(i+1);
     now+=37;
   }
   return fail_read?-1:0;
 }
 assert(n==1 && t[0].len==2 && t[0].buf[0]<128);
 registers[t[0].buf[0]]=t[0].buf[1];return 0;
}
bool PIOS_ESP32_I2C_Probe(uint32_t i,uint8_t a) { (void)i;(void)a;return true; }
int PIOS_SENSORS_Register(const PIOS_SENSORS_Driver *d,int t,uintptr_t c) {(void)d;(void)t;(void)c;return 1;}
void *pios_malloc(size_t n) { return calloc(1,n); }
int xQueueSend(void *q,const void *v,unsigned t) {
 (void)q;(void)t;assert(queue_item_size<=sizeof queue_copy);
 memcpy(queue_copy,v,queue_item_size);now+=queue_delay_us;return 1;
}
int xQueueReceive(void *q,void *v,unsigned t) {(void)q;(void)v;(void)t;return 1;}
void *xQueueCreate(unsigned n,unsigned s) {(void)n;queue_item_size=s;return (void *)1;}
void vQueueDelete(void *q) {(void)q;}
void vTaskNotifyGiveFromISR(void *t,int *w) {(void)t;(void)w;}
uint32_t ulTaskNotifyTake(int c,unsigned t) {(void)c; if(steps++) longjmp(stopped,1);if(missed_notification){now+=(int64_t)t*1000;return 0;}return 1;}
uint32_t xTaskGetTickCount(void) { return (uint32_t)(now/1000); }
int xTaskCreate(void (*f)(void *),const char *n,unsigned s,void *a,unsigned p,void **h) {
 (void)f;(void)n;(void)s;(void)a;(void)p;*h=(void *)1;return 1;
}
int gpio_config(const gpio_config_t *c) {(void)c;return 0;}
int gpio_install_isr_service(int f) {(void)f;return 0;}
int gpio_isr_handler_add(int g,void (*f)(void *),void *a) {(void)g;(void)f;(void)a;return 0;}
uint32_t UAVObjGetID(UAVObjHandle o) {return (uint32_t)(uintptr_t)o;}
uint16_t UAVObjGetNumBytes(UAVObjHandle o) {return UAVObjGetID(o)==LITEWINGIMUTIMING_OBJID?21:UAVObjGetID(o)==LITEWINGIMUHEALTH_OBJID?9:30;}
int32_t LiteWingIMUTimingInitialize(void) {return 0;}
UAVObjHandle LiteWingIMUTimingHandle(void) {return (void *)(uintptr_t)LITEWINGIMUTIMING_OBJID;}
int LiteWingIMUTimingGetMetadata(UAVObjMetadata *m) {m->flags=1;return 0;}
int32_t UAVObjPack(UAVObjHandle o,uint16_t i,uint8_t *b) {(void)o;(void)i; b[0]=42;return 7;}
int32_t LiteWingIMUHealthInitialize(void) {return is("register")?-1:0;}
UAVObjHandle LiteWingIMUHealthHandle(void) {return (void *)(uintptr_t)LITEWINGIMUHEALTH_OBJID;}
int LiteWingIMUHealthGetMetadata(UAVObjMetadata *m) {m->flags=1;return 0;}
int LiteWingIMUHealthSetMetadata(const UAVObjMetadata *m) {assert(m->telemetryUpdatePeriod==0);return 0;}
unsigned UAVObjGetGcsAccess(const UAVObjMetadata *m) {return m->flags;}
void UAVObjSetTelemetryUpdateMode(UAVObjMetadata *m,int mode) {(void)m;assert(mode==2);}
int LiteWingIMUHealthSet(const LiteWingIMUHealthData *d) {
 assert(d->Version==1); publications++;
 if(is("initial-publish") || (is("runtime-publish") && publications==3)) return -1;
 cached=*d;return 0;
}
int xTaskCreatePinnedToCore(void (*f)(void *),const char *n,unsigned s,void *a,unsigned p,void *h,int core) {
 assert(n && s>=2048 && !a && p==1 && !h && core==0);creates++;worker=f;return is("create")?0:1;
}
static void pack(uint8_t health,uint32_t age) {
 uint8_t b[30]; assert(LiteWingBatteryPack(LiteWingIMUHealthHandle(),0,b)==0);
 uint32_t got=(uint32_t)b[0]|(uint32_t)b[1]<<8|(uint32_t)b[2]<<16|(uint32_t)b[3]<<24;
 assert(b[4]==1 && b[8]==health && got==age);
}
void vTaskDelay(unsigned t) {
 if(run_sensor) return;
 assert(t==100);
 assert(cached.Health==1); /* previously stored healthy object remains cached */
 if(is("runtime-publish")) pack(0,UINT32_MAX);
 else { now+=20000;pack(0,20);assert(cached.Health==1); }
 longjmp(stopped,1);
}
static void sample(void) {steps=0;run_sensor=true;if(!setjmp(stopped))sensor_task(NULL);run_sensor=false;}
static atomic_bool done;
static void *compete(void *unused) {
 (void)unused;
 for(unsigned i=0;i<50000;i++) {
   uint64_t generation = invalidate_observation();
   record_identity(0x68, generation);
 }
 atomic_store(&done,true);return NULL;
}
int main(int argc,char **argv) {
 assert(argc==2);scenario=argv[1];run_sensor=true;
 if(strncmp(scenario,"mismatch-",9)==0 || strncmp(scenario,"readfail-",9)==0) {
   config_fault_reg=(int)strtoul(scenario+9,NULL,16);
   if(strlen(scenario)>11)config_fault_bit=(unsigned)strtoul(scenario+12,NULL,16);
   config_read_failure=strncmp(scenario,"readfail-",9)==0;
   assert(PIOS_LiteWing_MPU6050_Init(0,0x68)==-2);
   struct lw_imu_observation rejected;
   PIOS_LiteWing_MPU6050_GetObservation(&rejected);
   assert(!rejected.identity_verified && !device.healthy && !device.queue);
   puts("PASS");return 0;
 }
 assert(PIOS_LiteWing_MPU6050_Init(0,0x68)==0); run_sensor=false;
 if(is("failure-timing")) {
   struct lw_imu_timing measured;
   fail_read=true;transfer_delay_us=50000;sample();
   PIOS_LiteWing_MPU6050_GetTiming(&measured);
   assert(measured.read_failures==1 && measured.notification_timeouts==0);
   assert(measured.last_read_us==50000 && measured.max_read_us==50000);
   fail_read=false;transfer_delay_us=600;sample();
   PIOS_LiteWing_MPU6050_GetTiming(&measured);
   assert(measured.read_failures==1 && measured.last_read_us==600);
   assert(measured.max_read_us==50000);
   missed_notification=true;sample();
   PIOS_LiteWing_MPU6050_GetTiming(&measured);
   assert(measured.notification_timeouts==1 && measured.read_failures==1);
   assert(measured.last_wait_us==20000 && measured.last_read_us==0);
   uint8_t timing_wire[21];
   assert(LiteWingImuTimingPack((void *)(uintptr_t)0x5AF673A8,0,timing_wire)==0);
   const uint8_t expected[]={1,0,0,0,1,0,0,0,0x20,0x4e,0,0,0,0,0,0,0x50,0xc3,0,0,1};
   assert(memcmp(timing_wire,expected,sizeof expected)==0);
   assert(LiteWingImuTimingPack((void *)(uintptr_t)0x5AF673A8,1,timing_wire)==-1);
   free(queue_data);puts("PASS");return 0;
 }
 if(is("raw-provenance")) {
#if CONFIG_LRRK_ATTITUDE_TRACE
   assert(queue_item_size>LITEWING_MPU6050_DATA_SIZE);
#else
   assert(queue_item_size==LITEWING_MPU6050_DATA_SIZE);
#endif
   int64_t read_start=now;
   sample();
#if CONFIG_LRRK_ATTITUDE_TRACE
   struct lw_raw_sample provenance;
   lw_raw_queue_load(queue_copy,LITEWING_MPU6050_DATA_SIZE,&provenance);
   assert(provenance.sequence==0);
   assert(provenance.start_us==(uint32_t)read_start);
   assert(provenance.end_us==(uint32_t)(read_start+37));
   for(unsigned i=0;i<14;i++)assert(provenance.bytes[i]==i+1);
   sample();
   lw_raw_queue_load(queue_copy,LITEWING_MPU6050_DATA_SIZE,&provenance);
   assert(provenance.sequence==1);
#else
   (void)read_start;
#endif
   free(queue_data);puts("PASS");return 0;
 }
 struct lw_imu_observation o;
 PIOS_LiteWing_MPU6050_GetObservation(&o);assert(o.identity_verified && o.who_am_i==0x68 && !o.sample_seen);
 assert(LiteWingImuHealthStart()!=0);
 int rc=LiteWingImuHealthInitialize();
 if(is("register")||is("initial-publish")) {assert(rc!=0);pack(0,UINT32_MAX);puts("PASS");return 0;}
 assert(rc==0);pack(0,UINT32_MAX);
 assert((LiteWingImuHealthStart()==0)==!is("create"));assert(creates==1);
 assert(LiteWingImuHealthStart()!=0);
 if(is("create")) { sample();pack(0,UINT32_MAX);free(queue_data);puts("PASS");return 0; }
 if(is("queue-delay")) {
   queue_delay_us=21000;
   sample();
   pack(0,21); /* Queue publication must not renew a 21 ms old acquisition. */
   queue_delay_us=0;sample();pack(1,0);
   free(queue_data);puts("PASS");return 0;
 }
 if(is("reset-completion")) {
   pending_reset_generation=invalidate_observation();
   complete_reset_in_read=true;
   sample();
   PIOS_LiteWing_MPU6050_GetObservation(&o);
   assert(o.identity_verified && !o.sample_seen);
   pack(0,UINT32_MAX); /* A reset-period read cannot inherit later identity. */
   sample();pack(1,0); /* A subsequent validated acquisition is admissible. */
   free(queue_data);puts("PASS");return 0;
 }
 sample(); pack(1,0);
 now+=19000;pack(1,19);now+=1000;pack(0,20); /* explicit request and queued pack */
 now+=((int64_t)UINT32_MAX+1)*1000;pack(0,UINT32_MAX); /* full wrap cannot revive */
 sample();pack(1,0);fail_read=true;sample();pack(2,0);fail_read=false;
 PIOS_LiteWing_MPU6050_Shutdown();pack(0,UINT32_MAX);
 PIOS_LiteWing_MPU6050_GetObservation(&o);assert(!o.identity_verified && o.who_am_i==0 && !o.sample_seen);
 sample();pack(0,UINT32_MAX); /* shutdown cannot be undone by worker */
 run_sensor=true; driver_reset(0);run_sensor=false;
 sample();pack(1,0);reset_in_read=true;sample();pack(0,UINT32_MAX);
 identity=0x67;run_sensor=true;driver_reset(0);run_sensor=false;
 PIOS_LiteWing_MPU6050_GetObservation(&o);assert(!o.identity_verified);
 identity=0x68;run_sensor=true;driver_reset(0);run_sensor=false;sample();
 /* Shutdown during the final identity I2C transaction must win over an
  * in-flight configuration finishing on another task. */
 shutdown_on_identity_read=identity_reads+2;
 run_sensor=true;driver_reset(0);run_sensor=false;
 PIOS_LiteWing_MPU6050_GetObservation(&o);assert(!o.identity_verified && !o.sample_seen);
 run_sensor=true;driver_reset(0);run_sensor=false;sample();
 assert(publish_health()==0 && cached.Health==1);
 unsigned before=motor_writes;
 if(!is("create") && !setjmp(stopped))worker(NULL);
 assert(motor_writes==before); /* publication failure has no motor side effects */
 uint8_t b[30];assert(LiteWingBatteryPack((void *)3,0,b)==7 && b[0]==42);
 assert(LiteWingBatteryPack(LiteWingIMUHealthHandle(),1,b)==-1);
 assert(LiteWingBatteryPack(LiteWingIMUHealthHandle(),0,NULL)==-1);
 pthread_t thread;assert(pthread_create(&thread,NULL,compete,NULL)==0);
 do { PIOS_LiteWing_MPU6050_GetObservation(&o);
      assert((o.identity_verified && o.who_am_i==0x68) || (!o.identity_verified && o.who_am_i==0));
 } while(!atomic_load(&done));
 pthread_join(thread,NULL);free(queue_data);puts("PASS");
}
