/* Complete real System module and scheduler; other module and storage APIs
 * remain controlled boundaries. Reuse the scheduler RTOS ownership fixture. */
#include <openpilot.h>
#define xTaskCreate scheduler_create_task
#define vTaskDelete scheduler_delete_task
#define PIOS_TASK_MONITOR_RegisterTask scheduler_register_task
#define PIOS_TASK_MONITOR_UnregisterTask scheduler_unregister_task
#define main unused_scheduler_main
#include "scheduler_lifecycle_test.c"
#undef xTaskCreate
#undef vTaskDelete
#undef PIOS_TASK_MONITOR_RegisterTask
#undef PIOS_TASK_MONITOR_UnregisterTask
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
static bool lifecycle, early_system, executing_system, system_live, system_monitored, queue_live;
static unsigned system_creates, system_registers, system_unregisters, queue_creates, queue_deletes, object_inits;
static unsigned parked, module_inits;
int32_t SystemModStart(void);
void app_main(void);
uintptr_t pios_uavo_settings_fs_id, pios_user_fs_id;
volatile uint32_t uavobj_settings_generation;

static void run_system(void)
{
    CHECK(system_live && system_entry && !executing_system);
    executing_system = true;
    if (!setjmp(system_loop)) system_entry(NULL);
    executing_system = false;
}

BaseType_t xTaskCreate(TaskFunction_t entry, const char *name, uint32_t words,
                      void *arg, unsigned priority, void **out)
{
    if (!strcmp(name, "System")) {
        system_creates++;
        CHECK(words == 256 && priority == 1 && arg == NULL);
        CHECK(!system_live && !system_monitored && queue_live);
        if (!strcmp(scenario, "system-task")) return 0;
        system_entry = entry;
        system_live = true;
        if (out) *out = &system_token;
        if (early_system) run_system();
        return pdPASS;
    }
    return scheduler_create_task(entry, name, words, arg, priority, out);
}
void vTaskDelete(void *handle)
{
    if (!handle) {
        CHECK(executing_system && system_live);
        if (lifecycle) CHECK(!system_monitored && !queue_live);
        system_deletes++;
        system_live = false;
        longjmp(system_loop, 1);
    }
    scheduler_delete_task(handle);
}
int32_t PIOS_TASK_MONITOR_RegisterTask(uint16_t id, void *handle)
{
    if (id == TASKINFO_RUNNING_SYSTEM) {
        CHECK(handle == &system_token && system_live && !system_monitored);
        system_registers++;
        if (!strcmp(scenario, "system-monitor")) return -1;
        system_monitored = true;
        return 0;
    }
    return scheduler_register_task(id, handle);
}
int32_t PIOS_TASK_MONITOR_UnregisterTask(uint16_t id)
{
    if (id == TASKINFO_RUNNING_SYSTEM) {
        CHECK(executing_system && system_live && system_monitored);
        system_unregisters++;
        if (!strcmp(scenario, "system-unregister")) return -1;
        system_monitored = false;
        return 0;
    }
    return scheduler_unregister_task(id);
}
xTaskHandle xTaskGetCurrentTaskHandle(void)
{ CHECK(executing_system && system_live); return &system_token; }
void StartModules(void)
{
    if (lifecycle) CHECK(system_live && system_monitored && queue_live);
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

struct object { unsigned size; unsigned char data[1024]; bool present; };
#define OBJECT(Name) \
    static struct object obj_##Name = { .size = sizeof(Name##Data), .present = true }; \
    UAVObjHandle Name##Handle(void) { return obj_##Name.present ? &obj_##Name : NULL; } \
    int32_t Name##Initialize(void) { \
        object_inits++; \
        if (obj_##Name.present) return -2; \
        if (!strcmp(scenario, "object-" #Name)) return -1; \
        if (strcmp(scenario, "handle-" #Name)) obj_##Name.present = true; \
        return 0; \
    }
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
void vTaskDelay(unsigned ticks)
{
    CHECK(lifecycle && !strcmp(scenario, "system-unregister") && ticks == portMAX_DELAY);
    CHECK(system_live && system_monitored && shutdowns == 1 && fault_alarms == 1);
    parked++;
    /* A wake/finite tick wait must not fall through into deleting a handle
     * that the monitor still owns. Exercise two returns before stopping. */
    if (parked < 3) return;
    longjmp(system_loop, 1);
}
void PIOS_SYS_Reset(void) { CHECK(!"unexpected automatic reset"); }
xQueueHandle xQueueCreate(unsigned count, unsigned size)
{
    CHECK(count == 1 && size == sizeof(UAVObjEvent) && !queue_live);
    queue_creates++;
    if (!strcmp(scenario, "queue")) return NULL;
    queue_live = true;
    return &persistence_queue;
}
void vQueueDelete(xQueueHandle queue)
{
    CHECK(queue == &persistence_queue && queue_live && after_scheduler == 0);
    queue_live = false;
    queue_deletes++;
}
int xQueueReceive(xQueueHandle q, void *out, unsigned ticks)
{ (void)q; (void)out; (void)ticks; CHECK(!"unexpected persistence loop"); return 0; }
void PIOS_SYS_Init(void) {}
void PIOS_Board_Init(void) {}
bool PIOS_LiteWing_BoardServicesInitialized(void) { return true; }
void InitModules(void) { module_inits++; }

static void lifecycle_case(void)
{
    if (!strncmp(scenario, "entry-", 6)) {
        scenario += 6;
        if (!strcmp(scenario, "object-SystemStats")) obj_SystemStats.present = false;
        if (!strcmp(scenario, "handle-FlightStatus")) obj_FlightStatus.present = false;
        app_main();
        CHECK(module_inits == 1);
        if (strcmp(scenario, "nominal")) {
            CHECK(shutdowns == 1 && fault_alarms == 1 && module_starts == 0);
            CHECK(!system_live && !system_monitored && !queue_live);
        } else {
            CHECK(system_live && shutdowns == 0 && fault_alarms == 0);
            if (!early_system) run_system();
            CHECK(module_starts == 1 && after_scheduler == 3 && system_monitored);
        }
        return;
    }
    bool synchronous = !strncmp(scenario, "object-", 7) || !strncmp(scenario, "handle-", 7) ||
                       !strcmp(scenario, "queue") || !strcmp(scenario, "system-task");
    if (!strncmp(scenario, "object-", 7) || !strncmp(scenario, "handle-", 7) || !strcmp(scenario, "fresh")) {
        obj_SystemSettings.present = obj_SystemStats.present = false;
        obj_FlightStatus.present = obj_ObjectPersistence.present = false;
    }
    if (!strcmp(scenario, "direct-start")) {
        CHECK(SystemModStart() == -1 && system_creates == 0 && queue_creates == 0);
        return;
    }
    if (!strcmp(scenario, "scheduler-task") || !strcmp(scenario, "system-unregister")) fail_task = 2;
    if (!strcmp(scenario, "scheduler-monitor")) fail_monitor = 2;
    bool async_fault = fail_task || fail_monitor || !strcmp(scenario, "system-monitor");
    int32_t rc = SystemModInitialize();
    CHECK(rc == (synchronous ? -1 : 0));
    if (synchronous) {
        CHECK(!system_live && !system_monitored && !queue_live && module_starts == 0);
        CHECK(shutdowns == 0 && fault_alarms == 0);
        CHECK(queue_deletes == (!strcmp(scenario, "system-task") ? 1u : 0u));
    } else {
        if (!early_system) run_system();
        if (async_fault) {
            CHECK(shutdowns == 1 && fault_alarms == 1 && after_scheduler == 0);
            CHECK(queue_deletes == 1 && !queue_live);
            if (!strcmp(scenario, "system-unregister")) {
                CHECK(parked == 3 && system_live && system_monitored && system_deletes == 0);
            } else {
                CHECK(!system_live && !system_monitored && system_deletes == 1);
                CHECK(system_unregisters == (!strcmp(scenario, "system-monitor") ? 0u : 1u));
            }
            CHECK(module_starts == (!strcmp(scenario, "system-monitor") ? 0u : 1u));
            no_workers();
        } else {
            CHECK(system_live && system_monitored && queue_live && system_deletes == 0);
            CHECK(shutdowns == 0 && after_scheduler == 3 && module_starts == 1);
            CHECK(object_inits == (!strcmp(scenario, "fresh") ? 4u : 0u));
            execute_until_block(0);
            CHECK(callback_calls == 1);
        }
    }
    /* A boot caller must not allocate a second set, reset a live task's
     * flags, or retry after a failed attempt. */
    unsigned objects_before = object_inits, queues_before = queue_creates;
    unsigned creates_before = system_creates, registers_before = system_registers;
    CHECK(SystemModInitialize() == -1 && SystemModStart() == -1);
    CHECK(object_inits == objects_before && queue_creates == queues_before);
    CHECK(system_creates == creates_before && system_registers == registers_before);
}

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    scenario = argv[1];
    if (!strncmp(scenario, "life-", 5)) {
        lifecycle = true;
        scenario += 5;
        if (!strncmp(scenario, "early-", 6)) { early_system = true; scenario += 6; }
    }
    CHECK(PIOS_CALLBACKSCHEDULER_Initialize() == 0);
    if (lifecycle) { lifecycle_case(); return 0; }
    if (!strcmp(scenario, "task")) fail_task = 2;
    if (!strcmp(scenario, "monitor")) fail_monitor = 2;
    CHECK(SystemModInitialize() == 0 && system_entry);
    run_system();
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
