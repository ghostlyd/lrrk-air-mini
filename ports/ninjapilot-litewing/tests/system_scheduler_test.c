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
#include <pios_litewing_modules.h>

static TaskFunction_t system_entry;
static int system_token, persistence_queue;
static unsigned module_starts, after_scheduler, fault_alarms, shutdowns, system_deletes;
static unsigned readiness_checks;
static unsigned wifi_launches;
static unsigned usb_launches;
static bool lifecycle, early_system, executing_system, system_live, system_monitored, queue_live;
int lw_usb_maintenance_start(void)
{
    CHECK(readiness_checks==1 && after_scheduler==3 && system_live);
    CHECK(strcmp(scenario,"boot-readiness"));
    CHECK(wifi_launches==0);
    ++usb_launches;
    return !strcmp(scenario,"wifi-usb-task-failure") ? -1 : 0;
}
int lw_wifi_command_start(void)
{
    CHECK(readiness_checks==1 && after_scheduler==3 && system_live);
    CHECK(strcmp(scenario,"boot-readiness"));
    ++wifi_launches;
    return !strcmp(scenario,"wifi-task-failure") ? -1 : 0;
}
static jmp_buf system_loop;
static unsigned system_creates, system_registers, system_unregisters, queue_creates, queue_deletes, object_inits;
static unsigned parked, module_inits;
#ifdef TEST_MANUAL_MODULE
static bool manual_real_start, manual_start_in_progress;
/* The pinned implementation currently returns zero. This injection proves
 * only that ManualControl propagates a future/reported interface error. */
static bool manual_fail_configuration, manual_fail_alarm;
static unsigned manual_fail_start_connection;
static unsigned manual_configuration_checks, manual_alarm_clears, manual_frame_reads;
static unsigned manual_arm_init_calls, manual_arm_run_calls;
static unsigned manual_takeoff_init_calls, manual_takeoff_run_calls;
static unsigned manual_handler_calls, manual_flight_writes;
#endif
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
static void register_test_callbacks(void)
{
    if (lifecycle) CHECK(system_live && system_monitored && queue_live);
    module_starts++;
    DelayedCallbackInfo *cb = create(CALLBACK_TASK_FLIGHTCONTROL, 512);
    CHECK(cb && create(CALLBACK_TASK_AUXILIARY, 512));
    CHECK(PIOS_CALLBACKSCHEDULER_Dispatch(cb) == 0);
}
#ifndef TEST_MODULE_TABLE
int32_t PIOS_LiteWing_ModulesStart(void) { register_test_callbacks(); return 0; }
void StartModules(void) { register_test_callbacks(); }
#else
static unsigned init_calls, start_calls;
static int fail_init = -1, fail_start = -1;
#ifdef TEST_MANUAL_MODULE
int32_t RealManualControlInitialize(void);
int32_t RealManualControlStart(void);
static int32_t manual_start_result(unsigned index)
{
    if (index != 4 || !manual_real_start) return 0;
    CHECK(!manual_start_in_progress);
    manual_start_in_progress = true;
    int32_t result = RealManualControlStart();
    manual_start_in_progress = false;
    return result;
}
#define MANUAL_INIT_RESULT(Index) ((Index) == 4 ? RealManualControlInitialize() : 0)
#define MANUAL_START_RESULT(Index) manual_start_result(Index)
#else
#define MANUAL_INIT_RESULT(Index) 0
#define MANUAL_START_RESULT(Index) 0
#endif
#define MODULE(Name, Index) \
    int32_t Name##Initialize(void) { \
        CHECK(init_calls++ == Index); \
        return fail_init == Index ? -7 : MANUAL_INIT_RESULT(Index); \
    } \
    int32_t Name##Start(void) { \
        CHECK(start_calls++ == Index); \
        if (fail_start == Index) return -9; \
        int32_t result = MANUAL_START_RESULT(Index); \
        if (result != 0) return result; \
        if (Index == 5) register_test_callbacks(); \
        return 0; \
    }
MODULE(Attitude, 0)
MODULE(Stabilization, 1)
MODULE(Actuator, 2)
MODULE(Receiver, 3)
MODULE(ManualControl, 4)
MODULE(Telemetry, 5)
/* Preserve this fixture's six flight-module counters; battery_table_test.c
 * covers the seventh module and its failure propagation separately. */
int32_t LiteWingBatteryInitialize(void) { return 0; }
int32_t LiteWingBatteryStart(void) { return 0; }
int32_t LiteWingImuHealthInitialize(void) { return 0; }
int32_t LiteWingImuHealthStart(void) { return 0; }
#endif
void PIOS_LiteWing_BrushedPWM_Shutdown(void) { shutdowns++; }
int32_t AlarmsSet(SystemAlarmsAlarmElem alarm, SystemAlarmsAlarmOptions severity)
{
    CHECK(alarm == SYSTEMALARMS_ALARM_BOOTFAULT && severity == SYSTEMALARMS_ALARM_CRITICAL);
    CHECK(shutdowns == 1);
    fault_alarms++;
    return 0;
}
int32_t AlarmsClear(SystemAlarmsAlarmElem alarm)
{
#ifdef TEST_MANUAL_MODULE
    if (manual_start_in_progress) {
        CHECK(alarm == SYSTEMALARMS_ALARM_MANUALCONTROL);
        manual_alarm_clears++;
        return manual_fail_alarm ? -1 : 0;
    }
#endif
    (void)alarm;
    CHECK(!"unexpected alarm clear");
    return -1;
}
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
#ifdef TEST_MANUAL_MODULE
#include <manualcontrolcommand.h>
#include <manualcontrolsettings.h>
#include <flightmodesettings.h>
#include <stabilizationsettings.h>
#include <vtolselftuningstats.h>
#include <vtolpathfollowersettings.h>
OBJECT(ManualControlCommand)
OBJECT(ManualControlSettings)
OBJECT(FlightModeSettings)
OBJECT(StabilizationSettings)
OBJECT(VtolSelfTuningStats)
OBJECT(VtolPathFollowerSettings)
static unsigned manual_connections;
static UAVObjHandle manual_connection_objects[5];
static UAVObjEventCallback manual_connection_callbacks[5];
void armHandler(bool init, FrameType_t frame)
{
    CHECK(manual_real_start && frame == FRAME_TYPE_MULTIROTOR);
    if (init) manual_arm_init_calls++;
    else manual_arm_run_calls++;
}
void manualHandler(bool init)
{ CHECK(manual_real_start && init); manual_handler_calls++; }
void stabilizedHandler(bool init) { (void)init; CHECK(!"unexpected stabilized handler"); }
void pathFollowerHandler(bool init) { (void)init; CHECK(!"unexpected path follower handler"); }
void pathPlannerHandler(bool init) { (void)init; CHECK(!"unexpected path planner handler"); }
void takeOffLocationHandler(void)
{ CHECK(manual_real_start); manual_takeoff_run_calls++; }
void takeOffLocationHandlerInit(void)
{ CHECK(manual_real_start && manual_start_in_progress); manual_takeoff_init_calls++; }
void StabilizationSettingsFlightModeAssistMapGet(uint8_t *out)
{ (void)out; CHECK(!"unexpected runtime field read"); }
void VtolPathFollowerSettingsThrustLimitsGet(VtolPathFollowerSettingsThrustLimitsData *out)
{ CHECK(manual_real_start); memset(out, 0, sizeof(*out)); }
void VtolPathFollowerSettingsTreatCustomCraftAsGet(uint8_t *out)
{
    CHECK(manual_real_start && manual_start_in_progress);
    *out = VTOLPATHFOLLOWERSETTINGS_TREATCUSTOMCRAFTAS_VTOL;
}
void VtolSelfTuningStatsNeutralThrustOffsetGet(float *out)
{ (void)out; CHECK(!"unexpected runtime field read"); }
int32_t configuration_check(void)
{
    CHECK(manual_real_start && manual_start_in_progress);
    manual_configuration_checks++;
    return manual_fail_configuration ? -1 : 0;
}
#endif

int32_t UAVObjGetData(UAVObjHandle handle, void *out)
{ struct object *obj = handle; CHECK(obj && obj->size <= 1024); memcpy(out, obj->data, obj->size); return 0; }
int32_t UAVObjSetData(UAVObjHandle handle, const void *in)
{
#ifdef TEST_MANUAL_MODULE
    if (manual_real_start && handle == FlightStatusHandle()) {
        struct object *obj = handle;
        memcpy(obj->data, in, obj->size);
        manual_flight_writes++;
        return 0;
    }
#endif
    (void)handle; (void)in; CHECK(!"unexpected object write"); return -1;
}
int32_t UAVObjConnectQueue(UAVObjHandle obj, xQueueHandle queue, uint8_t mask)
{ (void)mask; CHECK(obj == ObjectPersistenceHandle() && queue == &persistence_queue); after_scheduler++; return !strcmp(scenario,"wifi-queue") ? -1 : 0; }
int32_t UAVObjConnectCallback(UAVObjHandle obj, UAVObjEventCallback cb, uint8_t mask)
{
    (void)obj; (void)cb; (void)mask;
#ifdef TEST_MANUAL_MODULE
    if (!executing_system || manual_start_in_progress) {
        CHECK(cb && mask == EV_MASK_ALL_UPDATES);
        CHECK(manual_connections < 5);
        const UAVObjHandle expected[] = {
            VtolPathFollowerSettingsHandle(), SystemSettingsHandle(),
            SystemSettingsHandle(), ManualControlSettingsHandle(), ManualControlCommandHandle(),
        };
        unsigned index = manual_connections++;
        CHECK(obj == expected[index]);
        manual_connection_objects[index] = obj;
        manual_connection_callbacks[index] = cb;
        if (index < 2) {
            if ((!strcmp(scenario, "connect-VtolPathFollowerSettings") && index == 0) ||
                (!strcmp(scenario, "connect-SystemSettings") && index == 1)) return -1;
        } else if (manual_fail_start_connection == index - 1) {
            return -1;
        }
        return 0;
    }
#endif
    after_scheduler++;
    if ((!strcmp(scenario,"wifi-hw-callback") && obj==HwSettingsHandle()) ||
        (!strcmp(scenario,"wifi-system-callback") && obj==SystemSettingsHandle())) return -1;
    return 0;
}
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
FrameType_t GetCurrentFrameType(void)
{
#ifdef TEST_MANUAL_MODULE
    if (manual_start_in_progress) manual_frame_reads++;
#endif
    return FRAME_TYPE_MULTIROTOR;
}
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
int32_t PIOS_LiteWing_ConfirmBootReady(void)
{
    readiness_checks++;
    return !strcmp(scenario, "boot-readiness") ? -1 : 0;
}
#ifndef TEST_MODULE_TABLE
int32_t PIOS_LiteWing_ModulesInitialize(void) { module_inits++; return 0; }
#endif

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

#ifdef TEST_MANUAL_MODULE
static unsigned manual_effect_count(void)
{
    return manual_configuration_checks + manual_connections + manual_alarm_clears +
           manual_frame_reads + manual_arm_init_calls + manual_arm_run_calls +
           manual_takeoff_init_calls + manual_takeoff_run_calls +
           manual_handler_calls + manual_flight_writes;
}

static void manual_start_case(void)
{
    lifecycle = true;
    manual_real_start = true;
    if (!strcmp(scenario, "premature")) {
        CHECK(manual_start_result(4) != 0);
        CHECK(manual_effect_count() == 0);
        return;
    }
    if (!strcmp(scenario, "configuration")) manual_fail_configuration = true;
    if (!strcmp(scenario, "alarm")) manual_fail_alarm = true;
    if (!strncmp(scenario, "connection-", 11)) {
        manual_fail_start_connection = (unsigned)atoi(scenario + 11);
        CHECK(manual_fail_start_connection >= 1 && manual_fail_start_connection <= 3);
    }
    bool nominal = !strcmp(scenario, "nominal");
    bool failed = !nominal;
    app_main();
    CHECK(init_calls == 6 && system_live && manual_connections == 2);
    run_system();
    CHECK(manual_configuration_checks == 1);
    if (failed) {
        unsigned expected_connections = 2;
        if (manual_fail_start_connection) expected_connections += manual_fail_start_connection;
        else if (manual_fail_alarm) expected_connections = 5;
        CHECK(manual_connections == expected_connections);
        CHECK(start_calls == 5 && shutdowns == 1 && fault_alarms == 1);
        CHECK(!system_live && !system_monitored && !queue_live && after_scheduler == 0);
        CHECK(task_calls == 0 && manual_arm_init_calls == 0 && manual_takeoff_init_calls == 0);
        CHECK(manual_alarm_clears == (unsigned)manual_fail_alarm);
        CHECK(manual_frame_reads == 0 && manual_arm_run_calls == 0 && manual_takeoff_run_calls == 0);
        unsigned effects = manual_effect_count();
        CHECK(manual_start_result(4) != 0 && manual_effect_count() == effects);
        return;
    }
    CHECK(start_calls == 6 && shutdowns == 0 && fault_alarms == 0);
    CHECK(system_live && system_monitored && queue_live && after_scheduler == 3);
    CHECK(manual_connections == 5 && manual_alarm_clears == 1 && manual_frame_reads == 1);
    CHECK(manual_arm_init_calls == 1 && manual_takeoff_init_calls == 1);
    CHECK(manual_connection_callbacks[0] == manual_connection_callbacks[1]);
    CHECK(manual_connection_callbacks[2] == manual_connection_callbacks[3]);
    CHECK(manual_connection_callbacks[2] != manual_connection_callbacks[0]);
    CHECK(manual_connection_callbacks[4] != manual_connection_callbacks[2]);
    CHECK(manual_connection_objects[2] == SystemSettingsHandle());
    CHECK(manual_connection_objects[3] == ManualControlSettingsHandle());
    CHECK(manual_connection_objects[4] == ManualControlCommandHandle());
    CHECK(task_calls == 2 && manual_arm_run_calls == 0 && manual_handler_calls == 0);
    execute_until_block(0);
    CHECK(manual_arm_run_calls == 1 && manual_takeoff_run_calls == 1);
    CHECK(manual_handler_calls == 1 && manual_flight_writes == 1 && callback_calls == 1);
    unsigned effects = manual_effect_count();
    CHECK(manual_start_result(4) != 0 && manual_effect_count() == effects);
}
#endif

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    scenario = argv[1];
    if (!strncmp(scenario, "early-table-", 12)) { early_system = true; scenario += 6; }
    if (!strncmp(scenario, "life-", 5)) {
        lifecycle = true;
        scenario += 5;
        if (!strncmp(scenario, "early-", 6)) { early_system = true; scenario += 6; }
    }
    CHECK(PIOS_CALLBACKSCHEDULER_Initialize() == 0);
    if (!strncmp(scenario,"wifi-",5)) {
        CHECK(SystemModInitialize()==0 && system_entry);
        run_system();
        CHECK(system_live && after_scheduler==3 && shutdowns==0 && fault_alarms==0);
        CHECK(wifi_launches==(!strcmp(scenario,"wifi-ready") ||
                             !strcmp(scenario,"wifi-task-failure") ||
                             !strcmp(scenario,"wifi-usb-task-failure") ? 1u : 0u));
        CHECK(usb_launches==wifi_launches);
        return 0;
    }
#ifdef TEST_MODULE_TABLE
#ifdef TEST_MANUAL_MODULE
    if (!strncmp(scenario, "manual-start-", 13)) {
        scenario += 13;
        manual_start_case();
        return 0;
    }
    if (!strncmp(scenario, "manual-", 7)) {
        scenario += 7;
        lifecycle = true;
        bool nominal = !strcmp(scenario, "nominal") || !strcmp(scenario, "fresh");
        if (!strcmp(scenario, "malloc1")) fail_malloc = 1;
        if (!strcmp(scenario, "malloc2")) fail_malloc = 2;
        if (!strcmp(scenario, "signal")) fail_signal = 1;
        if (!strcmp(scenario, "shared-malloc")) {
            CHECK(create(CALLBACK_TASK_FLIGHTCONTROL, 512));
            fail_malloc = 3;  /* New callback info, not the existing worker. */
        }
        if (!nominal || !strcmp(scenario, "fresh")) {
            obj_ManualControlCommand.present = obj_FlightStatus.present = false;
            obj_ManualControlSettings.present = obj_FlightModeSettings.present = false;
            obj_SystemSettings.present = obj_StabilizationSettings.present = false;
            obj_VtolSelfTuningStats.present = obj_VtolPathFollowerSettings.present = false;
        }
        app_main();
        if (!nominal) {
            CHECK(init_calls == 5 && start_calls == 0 && system_creates == 0);
            CHECK(shutdowns == 1 && fault_alarms == 1 && after_scheduler == 0);
            unsigned connections_before_failure = 0;
            if (fail_malloc || fail_signal || !strcmp(scenario, "connect-SystemSettings")) connections_before_failure = 2;
            if (!strcmp(scenario, "connect-VtolPathFollowerSettings")) connections_before_failure = 1;
            CHECK(manual_connections == connections_before_failure);
            if (!strcmp(scenario, "shared-malloc")) {
                CHECK(live_allocations == 2 && live_signals == 1 && !queue_live);
            } else {
                CHECK(live_allocations == 0 && live_signals == 0 && !queue_live);
            }
        } else {
            CHECK(init_calls == 6 && system_live && shutdowns == 0);
            CHECK(object_inits == (!strcmp(scenario, "fresh") ? 8u : 0u));
            CHECK(manual_connections == 2);
            run_system();
            CHECK(start_calls == 6 && after_scheduler == 3 && system_monitored);
            execute_until_block(0);
            CHECK(callback_calls == 1 && fault_alarms == 0);
        }
        return 0;
    }
#endif
    if (!strcmp(scenario, "table-order")) {
        CHECK(PIOS_LiteWing_ModulesStart() != 0 && start_calls == 0);
        CHECK(PIOS_LiteWing_ModulesInitialize() == 0 && init_calls == 6);
        CHECK(PIOS_LiteWing_ModulesInitialize() != 0 && init_calls == 6);
        CHECK(PIOS_LiteWing_ModulesStart() == 0 && start_calls == 6);
        CHECK(PIOS_LiteWing_ModulesStart() != 0 && start_calls == 6);
        return 0;
    }
    if (!strncmp(scenario, "table-", 6)) {
        lifecycle = true;
        if (!strncmp(scenario, "table-init-", 11)) fail_init = atoi(scenario + 11);
        if (!strncmp(scenario, "table-start-", 12)) fail_start = atoi(scenario + 12);
        app_main();
        if (fail_init >= 0) {
            CHECK(init_calls == (unsigned)fail_init + 1 && start_calls == 0);
            CHECK(shutdowns == 1 && fault_alarms == 1 && system_creates == 0);
            CHECK(queue_creates == 0 && after_scheduler == 0);
        } else {
            CHECK(init_calls == 6);
            if (!early_system) run_system();
            if (fail_start >= 0) {
                CHECK(start_calls == (unsigned)fail_start + 1);
                CHECK(shutdowns == 1 && fault_alarms == 1 && after_scheduler == 0);
                CHECK(!system_live && !system_monitored && !queue_live);
                CHECK(system_unregisters == 1 && system_deletes == 1);
                no_workers();
            } else {
                CHECK(start_calls == 6 && after_scheduler == 3 && system_monitored);
                CHECK(shutdowns == 0 && fault_alarms == 0);
                execute_until_block(0);
                CHECK(callback_calls == 1);
            }
        }
        unsigned inits_before = init_calls, starts_before = start_calls;
        CHECK(PIOS_LiteWing_ModulesInitialize() != 0);
        CHECK(PIOS_LiteWing_ModulesStart() != 0);
        CHECK(init_calls == inits_before && start_calls == starts_before);
        return 0;
    }
#endif
    if (lifecycle) { lifecycle_case(); return 0; }
    if (!strcmp(scenario, "task")) fail_task = 2;
    if (!strcmp(scenario, "monitor")) fail_monitor = 2;
    CHECK(SystemModInitialize() == 0 && system_entry);
    run_system();
    CHECK(module_starts == 1);
    CHECK(readiness_checks == (!strcmp(scenario, "task") || !strcmp(scenario, "monitor") ? 0u : 1u));
    if (strcmp(scenario, "nominal")) {
        CHECK(wifi_launches==0);
        CHECK(shutdowns == 1 && fault_alarms == 1 && system_deletes == 1);
        CHECK(after_scheduler == 0);
        if (!strcmp(scenario, "boot-readiness")) {
            /* A post-start readiness failure permanently latches outputs off.
             * Scheduler workers are not deleted while they may own callback
             * state; the process remains faulted and performs no normal boot
             * connections. */
            CHECK(task_calls == 2);
            for (unsigned n = 0; n < task_calls; ++n) {
                CHECK(tasks[n].live && tasks[n].monitored);
            }
        } else {
            no_workers();
        }
    } else {
        CHECK(shutdowns == 0 && fault_alarms == 0 && system_deletes == 0);
        CHECK(after_scheduler == 3);
        execute_until_block(0);
        CHECK(callback_calls == 1);
    }
    return 0;
}
