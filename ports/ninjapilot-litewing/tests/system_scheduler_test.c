/* Complete real System module and scheduler; other module and storage APIs
 * remain controlled boundaries. Reuse the scheduler RTOS ownership fixture. */
#include <openpilot.h>
#define xTaskCreate scheduler_create_task
#define vTaskDelete scheduler_delete_task
#define PIOS_TASK_MONITOR_RegisterTask scheduler_register_task
#define main unused_scheduler_main
#include "scheduler_lifecycle_test.c"
#undef xTaskCreate
#undef vTaskDelete
#undef PIOS_TASK_MONITOR_RegisterTask
#undef main
#include <systemmod.h>
#include <systemstats.h>
#include <systemsettings.h>
#include <settingsgeneration.h>
#include <flightstatus.h>
#include <objectpersistence.h>
#include <hwsettings.h>
#include <pios_flashfs.h>
#include <sanitycheck.h>

static TaskFunction_t system_entry;
static int system_token, persistence_queue;
static unsigned module_starts, after_scheduler, fault_alarms, shutdowns, system_deletes;
static jmp_buf system_loop;
uintptr_t pios_uavo_settings_fs_id, pios_user_fs_id;
volatile uint32_t uavobj_settings_generation;

BaseType_t xTaskCreate(TaskFunction_t entry, const char *name, uint32_t words,
                      void *arg, unsigned priority, void **out)
{
    if (!strcmp(name, "System")) { system_entry = entry; *out = &system_token; return pdPASS; }
    return scheduler_create_task(entry, name, words, arg, priority, out);
}
void vTaskDelete(void *handle)
{
    if (!handle) { system_deletes++; return; }
    scheduler_delete_task(handle);
}
int32_t PIOS_TASK_MONITOR_RegisterTask(uint16_t id, void *handle)
{
    if (id == TASKINFO_RUNNING_SYSTEM) { CHECK(handle == &system_token); return 0; }
    return scheduler_register_task(id, handle);
}
void StartModules(void)
{
    module_starts++;
    DelayedCallbackInfo *cb = create(CALLBACK_TASK_FLIGHTCONTROL, 512);
    CHECK(cb && create(CALLBACK_TASK_AUXILIARY, 512));
    CHECK(PIOS_CALLBACKSCHEDULER_Dispatch(cb) == 0);
}
void PIOS_LiteWing_BrushedPWM_Shutdown(void) { shutdowns++; }
int32_t AlarmsSet(SystemAlarmsAlarmElem alarm, SystemAlarmsAlarmOptions severity)
{
    CHECK(alarm == SYSTEMALARMS_ALARM_BOOTFAULT && severity == SYSTEMALARMS_ALARM_CRITICAL);
    CHECK(shutdowns == 1);
    fault_alarms++;
    return 0;
}
int32_t AlarmsClear(SystemAlarmsAlarmElem alarm) { (void)alarm; CHECK(!"unexpected alarm clear"); return -1; }
int32_t ExtendedAlarmsSet(SystemAlarmsAlarmElem alarm, SystemAlarmsAlarmOptions severity,
    SystemAlarmsExtendedAlarmStatusOptions status, uint8_t substatus)
{ (void)alarm; (void)severity; (void)status; (void)substatus; CHECK(!"unexpected extended alarm write"); return -1; }

struct object { unsigned size; unsigned char data[1024]; };
#define OBJECT(Name) \
    static struct object obj_##Name = { .size = sizeof(Name##Data) }; \
    UAVObjHandle Name##Handle(void) { return &obj_##Name; } \
    int32_t Name##Initialize(void) { return 0; }
OBJECT(SystemStats)
OBJECT(SystemSettings)
OBJECT(SettingsGeneration)
OBJECT(FlightStatus)
OBJECT(ObjectPersistence)
OBJECT(HwSettings)

int32_t UAVObjGetData(UAVObjHandle handle, void *out)
{ struct object *obj = handle; CHECK(obj && obj->size <= 1024); memcpy(out, obj->data, obj->size); return 0; }
int32_t UAVObjSetData(UAVObjHandle handle, const void *in)
{ (void)handle; (void)in; CHECK(!"unexpected object write"); return -1; }
int32_t UAVObjConnectQueue(UAVObjHandle obj, xQueueHandle queue, uint8_t mask)
{ (void)mask; CHECK(obj == ObjectPersistenceHandle() && queue == &persistence_queue); after_scheduler++; return 0; }
int32_t UAVObjConnectCallback(UAVObjHandle obj, UAVObjEventCallback cb, uint8_t mask)
{ (void)obj; (void)cb; (void)mask; after_scheduler++; return 0; }
UAVObjHandle UAVObjGetByID(uint32_t id) { (void)id; CHECK(!"unexpected lookup"); return NULL; }
#define PERSIST_ONE(Name) int32_t Name(UAVObjHandle obj, uint16_t inst) { (void)obj; (void)inst; CHECK(!"unexpected persistence"); return -1; }
#define PERSIST_ALL(Name) int32_t Name(void) { CHECK(!"unexpected persistence"); return -1; }
PERSIST_ONE(UAVObjLoad)
PERSIST_ONE(UAVObjSave)
PERSIST_ONE(UAVObjDelete)
PERSIST_ALL(UAVObjLoadSettings)
PERSIST_ALL(UAVObjLoadMetaobjects)
PERSIST_ALL(UAVObjSaveSettings)
PERSIST_ALL(UAVObjSaveMetaobjects)
PERSIST_ALL(UAVObjDeleteSettings)
PERSIST_ALL(UAVObjDeleteMetaobjects)
void UAVObjGetStats(UAVObjStats *out) { memset(out, 0, sizeof(*out)); }
void UAVObjClearStats(void) {}
void EventGetStats(EventStats *out) { memset(out, 0, sizeof(*out)); }
void EventClearStats(void) {}
int32_t PIOS_FLASHFS_GetStats(uintptr_t id, struct PIOS_FLASHFS_Stats *out)
{ (void)id; (void)out; CHECK(!"unexpected storage access"); return -1; }
FrameType_t GetCurrentFrameType(void) { return FRAME_TYPE_MULTIROTOR; }
void NotificationUpdateStatus(void) { longjmp(system_loop, 1); }
void NotificationOnboardLedsRun(void) {}
unsigned xPortGetFreeHeapSize(void) { return 10000; }
unsigned uxTaskGetStackHighWaterMark(xTaskHandle task) { (void)task; return 1000; }
uint8_t PIOS_TASK_MONITOR_GetIdlePercentage(void) { return 50; }
void vTaskDelay(unsigned ticks) { (void)ticks; CHECK(!"unexpected delay"); }
void PIOS_SYS_Reset(void) { CHECK(!"unexpected automatic reset"); }
xQueueHandle xQueueCreate(unsigned count, unsigned size)
{ CHECK(count == 1 && size == sizeof(UAVObjEvent)); return &persistence_queue; }
int xQueueReceive(xQueueHandle q, void *out, unsigned ticks)
{ (void)q; (void)out; (void)ticks; CHECK(!"unexpected persistence loop"); return 0; }

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    scenario = argv[1];
    CHECK(PIOS_CALLBACKSCHEDULER_Initialize() == 0);
    if (!strcmp(scenario, "task")) fail_task = 2;
    if (!strcmp(scenario, "monitor")) fail_monitor = 2;
    CHECK(SystemModInitialize() == 0 && system_entry);
    if (!setjmp(system_loop)) system_entry(NULL);
    CHECK(module_starts == 1);
    if (strcmp(scenario, "nominal")) {
        CHECK(shutdowns == 1 && fault_alarms == 1 && system_deletes == 1);
        CHECK(after_scheduler == 0);
        no_workers();
    } else {
        CHECK(shutdowns == 0 && fault_alarms == 0 && system_deletes == 0);
        CHECK(after_scheduler == 3);
        execute_until_block(0);
        CHECK(callback_calls == 1);
    }
    return 0;
}
