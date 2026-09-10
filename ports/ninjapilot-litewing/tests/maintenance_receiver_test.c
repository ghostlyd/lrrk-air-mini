#include "uavobjectmanager.h"
#include "pios_gcsrcvr_priv.h"
#include "pios_litewing_gcsrcvr.h"
#include <assert.h>
#include <string.h>

static int64_t now=1000;
static GCSReceiverData object;
static unsigned writes, loads;
static const uint8_t owner[16]={1};
int64_t esp_timer_get_time(void) { return now; }
UAVObjHandle GCSReceiverHandle(void) { return &object; }
static void reject_during_write(void) {
    uint64_t token=99;
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&token)==-1 && token==0);
}
int32_t UAVObjUnpack(UAVObjHandle h,uint16_t instance,const uint8_t *bytes) {
    assert(h==&object && instance==0); ++writes; reject_during_write();
    memcpy(&object,bytes,sizeof(object)); return 0;
}
static int32_t load(UAVObjHandle h,uint16_t instance) {
    assert(h==&object && instance==0); ++loads; reject_during_write(); return 0;
}
int main(void) {
    uint64_t token=99, other=99, old;
    uint32_t id;
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&token)==-1 && token==0);
    assert(PIOS_GCSRCVR_Init(&id)==0);
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(0,&token)==-1 && token==0);
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,NULL)==-1);
    assert(!PIOS_LiteWing_GCSReceiver_MaintenanceHeld(0));
    assert(PIOS_LiteWing_GCSReceiver_BeginAdmission(1,&other)==0);
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&token)==-1);
    assert(PIOS_LiteWing_GCSReceiver_EndAdmission(other)==0);
    ++now;
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&token)==0 && token);
    old=token;
    assert(PIOS_LiteWing_GCSReceiver_MaintenanceHeld(token));
    assert(!PIOS_LiteWing_GCSReceiver_MaintenanceHeld(token+1));
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&other)==-1 && other==0);
    assert(PIOS_LiteWing_GCSReceiver_BeginAdmission(1,&other)==-1 && other==0);
    assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(owner,1)==-1);
    assert(PIOS_LiteWing_GCSReceiver_EndAdmission(token)==-1);
    assert(PIOS_LiteWing_GCSReceiver_EndMaintenance(token+1)==-1);
    GCSReceiverData input={.Channel={1500}};
    ++now;
    assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(uint8_t *)&input,now)==-1);
    assert(PIOS_LiteWing_GCSReceiver_SettingsLoad(&object,0,load)==-1);
    assert(!writes && !loads);
    now=500;
    assert(!PIOS_LiteWing_GCSReceiver_MaintenanceHeld(token));
    assert(PIOS_LiteWing_GCSReceiver_EndMaintenance(token)==-1);
    assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(owner,1)==-1);
    now=2000;
    assert(PIOS_LiteWing_GCSReceiver_MaintenanceHeld(token));
    assert(PIOS_LiteWing_GCSReceiver_EndMaintenance(token)==0);
    assert(!PIOS_LiteWing_GCSReceiver_MaintenanceHeld(token));
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&token)==0 && token!=old);
    assert(PIOS_LiteWing_GCSReceiver_EndMaintenance(old)==-1);
    assert(PIOS_LiteWing_GCSReceiver_EndMaintenance(token)==0);
    ++now;
    assert(PIOS_LiteWing_GCSReceiver_SettingsLoad(&object,0,load)==0 && loads==1);
    assert(PIOS_LiteWing_GCSReceiver_Unpack(&object,0,(uint8_t *)&input,now)==0 && writes==1);
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&token)==-1);
    now+=100000;
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&token)==0);
    assert(PIOS_LiteWing_GCSReceiver_EndMaintenance(token)==0);
    assert(PIOS_LiteWing_GCSReceiver_ClaimWireless(owner,1)==0);
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&token)==-1);
    assert(PIOS_LiteWing_GCSReceiver_ReleaseWireless(owner,1)==0);
    assert(PIOS_LiteWing_GCSReceiver_BeginMaintenance(1,&token)==0);
    assert(PIOS_LiteWing_GCSReceiver_EndMaintenance(token)==0);
    return 0;
}
