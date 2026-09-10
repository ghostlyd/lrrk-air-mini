#include "pios_litewing_gcsrcvr.h"
#include "pios_gcsrcvr_priv.h"
#include <assert.h>
#include <string.h>

static int storage, calls, fail, check_admission;
static GCSReceiverData channels;
static uint8_t identity[16]={1};
int64_t esp_timer_get_time(void) { return 1000; }
UAVObjHandle GCSReceiverHandle(void) { return &channels; }
int32_t UAVObjUnpack(UAVObjHandle obj,uint16_t i,const uint8_t *b)
{ (void)obj; (void)i; (void)b; assert(0); return -1; }
int32_t UAVObjLoad(UAVObjHandle,uint16_t);
int32_t UAVObjLoad_unserialized(UAVObjHandle obj,uint16_t instance) {
    assert(obj==&storage && instance==7); ++calls;
    if(check_admission) {
        uint64_t token=0;
        assert(PIOS_LiteWing_GCSReceiver_BeginAdmission(1,&token)==-1);
        assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(identity,1)==-1);
    }
    if(fail) return -7;
    ++storage; return 0;
}
int main(void) {
    /* Boot registration loads remain possible. */
    assert(UAVObjLoad(&storage,7)==0 && storage==1);
    uint32_t receiver=0;
    assert(PIOS_GCSRCVR_Init(&receiver)==0);
    uint64_t token=0;
    assert(PIOS_LiteWing_GCSReceiver_BeginAdmission(1,&token)==0);
    assert(UAVObjLoad(&storage,7)==-1 && storage==1 && calls==1);
    assert(PIOS_LiteWing_GCSReceiver_EndAdmission(token)==0);
    check_admission=1;
    assert(UAVObjLoad(&storage,7)==0 && storage==2);
    fail=1; assert(UAVObjLoad(&storage,7)==-7 && storage==2);
    assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(identity,1)==0);
    assert(UAVObjLoad(&storage,7)==-1 && calls==3 && storage==2);
    assert(PIOS_LiteWing_GCSReceiver_ReleaseWireless(identity,1)==0);
    fail=0; assert(UAVObjLoad(&storage,7)==0 && calls==4 && storage==3);
    assert(UAVObjLoad(NULL,7)==-1 && calls==4);
    assert(pios_gcsrcvr_rcvr_driver.read(receiver,0)==PIOS_RCVR_TIMEOUT);
    return 0;
}
