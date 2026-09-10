#include "pios_litewing_usb_maintenance.h"
#include "pios_litewing_gcsrcvr.h"
#include "pios_gcsrcvr_priv.h"
#include "litewing_wifi_store.h"
#include "flightstatus.h"
#include <freertos/task.h>
#include <assert.h>
#include <setjmp.h>
#include <string.h>

static const char *scenario;
static int64_t now=1000;
static unsigned notifications, writes, stop_calls, delay_calls;
static TaskFunction_t worker;
static void *worker_arg;
static jmp_buf idle;
static uint8_t request[152], expected[136];
static GCSReceiverData receiver;
static const uint8_t owner[16]={2};
#define CASE(name) (!strcmp(scenario,name))
int64_t esp_timer_get_time(void) { return now; }
UAVObjHandle GCSReceiverHandle(void) { return &receiver; }
int32_t UAVObjUnpack(UAVObjHandle h,uint16_t i,const uint8_t *data) {
    assert(h==&receiver && i==0); memcpy(&receiver,data,sizeof(receiver)); return 0;
}
int32_t FlightStatusGet(FlightStatusData *out) {
    memset(out,0,sizeof(*out));
    out->Armed=(CASE("armed") || (CASE("arm-during-stop") && stop_calls)) ? 2 : 0;
    return CASE("flight-read-error") ? -1 : 0;
}
BaseType_t xTaskCreate(TaskFunction_t fn,const char *name,uint32_t stack,void *arg,
                       UBaseType_t priority,TaskHandle_t *handle) {
    (void)name; (void)priority; assert(stack>=4096);
    if (CASE("create-fail")) return 0;
    worker=fn; worker_arg=arg; *handle=(TaskHandle_t)&worker; return pdPASS;
}
void xTaskNotifyGive(TaskHandle_t task) { assert(task==(TaskHandle_t)&worker); ++notifications; }
uint32_t ulTaskNotifyTake(BaseType_t clear,TickType_t wait) {
    assert(clear==pdTRUE && wait==portMAX_DELAY);
    if (!notifications) longjmp(idle,1);
    unsigned count=notifications; notifications=0; return count;
}
static void status(uint8_t phase,uint8_t result) {
    uint8_t wire[24]; memset(wire,0xA5,sizeof(wire));
    assert(lw_usb_maintenance_status(wire,sizeof(wire))==24);
    assert(wire[0]==1 && wire[1]==phase && wire[2]==result && wire[3]==0);
    assert(!memcmp(wire+4,request,16));
    for (unsigned i=20;i<24;++i) assert(wire[i]==0);
}
static void reject_new_valid_request(void) {
    uint8_t another[152]={3}; memcpy(another+16,expected,136);
    assert(lw_usb_maintenance_submit(another,sizeof(another))==-1);
}
void vTaskDelay(TickType_t ticks) {
    assert(ticks); ++delay_calls;
    if (CASE("cleanup") && writes) {
        status(5,4); reject_new_valid_request();
        assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(owner,1)==-1);
        now=3000000;
    } else if (CASE("rollback")) {
        uint8_t wire[24]; assert(lw_usb_maintenance_status(wire,24)==24);
        now=wire[1]==5 ? 3000000 : 500;
    }
    else now+=(int64_t)ticks*1000;
}
void lw_wifi_command_request_stop(void) { ++stop_calls; }
int lw_wifi_command_is_quiescent(void) {
    if (CASE("timeout")) return now>=2001000; /* deadline must win over late exit */
    if (CASE("rollback")) return 0;
    return 1;
}
enum lw_wifi_store_result lw_wifi_config_store(const uint8_t *blob,size_t size) {
    assert(size==136 && !memcmp(blob,expected,136)); assert(stop_calls==1);
    status(4,0);
    uint64_t token=0;
    assert(PIOS_LiteWing_GCSReceiver_BeginAdmission(1,&token)==-1);
    assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(owner,1)==-1);
    assert(PIOS_LiteWing_GCSReceiver_Unpack(&receiver,0,(uint8_t *)&receiver,now)==-1);
    FlightStatusData flight; assert(FlightStatusGet(&flight)==0 && flight.Armed==0);
    assert(lw_wifi_command_is_quiescent()); ++writes;
    reject_new_valid_request();
    if (CASE("cleanup")) now=500; /* actual receiver refuses token cleanup */
    if (CASE("uncertain")) return LW_WIFI_STORE_UNCERTAIN;
    if (CASE("not-written")) return LW_WIFI_STORE_NOT_WRITTEN;
    if (CASE("invalid-store")) return LW_WIFI_STORE_INVALID;
    return LW_WIFI_STORE_VERIFIED;
}
int main(int argc,char **argv) {
    assert(argc==2); scenario=argv[1]; uint32_t id;
    request[0]=1; memcpy(request+16,"LWCF",4);
    request[20]=1; request[21]=1; request[22]=16; request[24]=42;
    request[56]='x'; memset(request+88,'p',16); memcpy(expected,request+16,136);
    assert(lw_usb_maintenance_submit(request,sizeof(request))==-1);
    assert(lw_usb_maintenance_status(NULL,24)==-1);
    uint8_t short_out[23]; memset(short_out,0xA5,sizeof(short_out));
    assert(lw_usb_maintenance_status(short_out,23)==-1);
    for (unsigned i=0;i<23;++i) assert(short_out[i]==0xA5);
    assert(PIOS_GCSRCVR_Init(&id)==0);
    if (CASE("create-fail")) {
        assert(lw_usb_maintenance_start()==-1);
        assert(lw_usb_maintenance_submit(request,sizeof(request))==-1); return 0;
    }
    assert(lw_usb_maintenance_start()==0);
    assert(lw_usb_maintenance_start()==-1);
    uint8_t malformed[152]; memcpy(malformed,request,sizeof(malformed));
    memset(malformed,0,16); assert(lw_usb_maintenance_submit(malformed,152)==-1);
    memcpy(malformed,request,152); malformed[23]=1;
    assert(lw_usb_maintenance_submit(malformed,152)==-1);
    assert(lw_usb_maintenance_submit(NULL,152)==-1);
    assert(lw_usb_maintenance_submit(request,151)==-1);
    uint64_t admission=0;
    if (CASE("owner")) assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(owner,1)==0);
    if (CASE("admission")) assert(PIOS_LiteWing_GCSReceiver_BeginAdmission(1,&admission)==0);
    if (CASE("fresh-input")) {
        receiver.Channel[0]=1500;
        assert(PIOS_LiteWing_GCSReceiver_Unpack(&receiver,0,(uint8_t *)&receiver,++now)==0);
    }
    assert(lw_usb_maintenance_submit(request,152)==0); status(2,0);
    memcpy(malformed,request,152); ++malformed[0];
    assert(lw_usb_maintenance_submit(malformed,152)==-1);
    /* Caller can wipe/change input immediately after submit returns. */
    memset(request+16,0,136);
    if (!setjmp(idle)) worker(worker_arg);
    int stored=CASE("success") || CASE("cleanup") || CASE("uncertain") ||
               CASE("not-written") || CASE("invalid-store");
    assert(writes==(unsigned)stored);
    uint8_t result= !stored ? 0 : CASE("uncertain") ? 3 : CASE("not-written") ? 2 :
                    CASE("invalid-store") ? 1 : 4;
    status(6,result);
    memcpy(request+16,expected,136);
    assert(lw_usb_maintenance_submit(request,152)==-1); /* retained transaction ID */
    request[56]='z';
    assert(lw_usb_maintenance_submit(request,152)==-1); /* changed valid credentials, same ID */
    if (CASE("cleanup")) assert(delay_calls==1 && writes==1);
    if (CASE("timeout")) assert(now==2001000 && delay_calls==200);
    if (CASE("owner") || CASE("admission") || CASE("fresh-input") ||
        CASE("armed") || CASE("flight-read-error")) assert(stop_calls==0);
    if (admission) assert(PIOS_LiteWing_GCSReceiver_EndAdmission(admission)==0);
    if (CASE("owner")) assert(PIOS_LiteWing_GCSReceiver_ReleaseWireless(owner,1)==0);
    now=4000000;
    assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(owner,1)==0);
    assert(PIOS_LiteWing_GCSReceiver_ReleaseWireless(owner,1)==0);
    request[0]=3;
    assert(lw_usb_maintenance_submit(request,152)==0); /* next transaction accepted only after cleanup */
    status(2,0);
    return 0;
}
