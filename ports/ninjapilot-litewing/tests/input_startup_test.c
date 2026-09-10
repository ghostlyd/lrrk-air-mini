/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Actual complete input module and module table, generated UAVObjects and math.
 * Controlled store/RTOS/driver boundaries; no device or physical output I/O. */
#include <openpilot.h>
#include <stdio.h>
#include <setjmp.h>
#include <pios_sensors.h>
#include <pios_notify.h>
#include <pios_board_info.h>
#include <pios_litewing_modules.h>
#include <sanitycheck.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL: %s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#ifdef __clang__
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wparentheses-equality"
#pragma clang diagnostic ignored "-Wunknown-attributes"
#endif
#include MODULE_SOURCE
#ifdef __clang__
#pragma clang diagnostic pop
#endif

#ifdef TEST_ATTITUDE
#define INPUT_INIT AttitudeInitialize
#define INPUT_START AttitudeStart
#define INPUT_NAME "Attitude"
#define INPUT_MONITOR TASKINFO_RUNNING_ATTITUDE
#define INPUT_WDG PIOS_WDG_ATTITUDE
#define INPUT_OBJECTS 5
#define LATER_MODULES 5
#define INPUT_STACK_WORDS (PIOS_ATTITUDE_STACK_SIZE / 4)
#else
#define INPUT_INIT ReceiverInitialize
#define INPUT_START ReceiverStart
#define INPUT_NAME "Receiver"
#define INPUT_MONITOR TASKINFO_RUNNING_RECEIVER
#define INPUT_WDG PIOS_WDG_MANUAL
#define INPUT_OBJECTS 7
#define LATER_MODULES 2
#define INPUT_STACK_WORDS (PIOS_RECEIVER_STACK_SIZE / 4)
#endif

struct object { uint32_t id, size; unsigned instances; unsigned char data[3][2048]; UAVObjMetadata metadata; };
static struct object objects[16];
struct subscription { UAVObjHandle obj; UAVObjEventCallback cb; uint8_t mask; };
static struct subscription subscriptions[2];
static unsigned object_count, registrations, connections, subscription_count, allocations, instance_calls;
static unsigned creates, monitor_calls, unregisters, task_deletes, parked, watchdog_calls;
static unsigned shutdowns, fault_alarms, loop_waits, later_inits, later_starts, sensor_tests, scales;
static unsigned frame_queries;
static unsigned output_handle_requests;
static int fail_object, fail_callback, fail_instance;
static bool fail_instance_zero, fail_instance_grown, fail_allocation, fail_watchdog, fail_task, fail_monitor, fail_unregister;
static bool fail_test, fail_sensor_queue, fail_init_read, fail_init_write, fail_command_read, fail_flight_read;
static bool in_registration, in_worker, worker_live, monitored, early;
static int task_token, sensor_queue_token;
static void (*worker_entry)(void *);
static jmp_buf worker_exit;
static SystemAlarmsAlarmOptions alarms[SYSTEMALARMS_ALARM_NUMELEM];
const struct pios_board_info pios_board_info_blob = { .board_rev = 0x02 };
uint32_t pios_rcvr_group_map[8] = { 1, 1, 1, 1, 1, 1, 1, 1 };

static void check_initial_settings(void) {
#ifdef TEST_ATTITUDE
    CHECK(scales == 1 && rotate == 1);
    CHECK(gyro_scale.X == 4.5f && gyro_scale.Y == 6.0f && gyro_scale.Z == 7.5f);
    CHECK(accel_scale.X == 2.5f && accel_scale.Y == 3.0f && accel_scale.Z == 3.5f);
    /* Seeded 90-degree yaw, not the zero/default board rotation. */
    CHECK(fabsf(R[0][0]) < 1e-5f && fabsf(R[0][1] - 1.0f) < 1e-5f);
    CHECK(fabsf(R[1][0] + 1.0f) < 1e-5f && fabsf(R[1][1]) < 1e-5f);
    CHECK(fabsf(R[2][2] - 1.0f) < 1e-5f);
#else
    CHECK(frame_queries == 1 && frameType == FRAME_TYPE_GROUND);
#endif
}

UAVObjHandle UAVObjGetByID(uint32_t id) {
    for (unsigned i = 0; i < object_count; ++i) if (objects[i].id == id) return &objects[i];
    return NULL;
}
UAVObjHandle UAVObjRegister(uint32_t id, bool single, bool settings, bool priority,
                           uint32_t size, UAVObjInitializeCallback cb) {
    if (++registrations == (unsigned)fail_object) return NULL;
    CHECK(object_count < 16 && size <= 2048 && !UAVObjGetByID(id));
    struct object *o = &objects[object_count++]; o->id = id; o->size = size; o->instances = 1;
    in_registration = true; cb(o, 0); in_registration = false; return o;
}
static bool deny_read(struct object *o) {
    if (in_worker) CHECK(monitored);
    if (in_registration) return false;
#ifdef TEST_ATTITUDE
    return !in_worker && fail_init_read && o->id == ATTITUDESTATE_OBJID;
#else
    return in_worker && ((fail_command_read && o->id == MANUALCONTROLCOMMAND_OBJID) ||
                         (fail_flight_read && o->id == FLIGHTSTATUS_OBJID));
#endif
}
int32_t UAVObjGetInstanceData(UAVObjHandle h, uint16_t instance, void *out) {
    if (!h) return -1;
    struct object *o = h; CHECK(instance < o->instances);
    if (deny_read(o)) return -1;
    memcpy(out, o->data[instance], o->size); return 0;
}
int32_t UAVObjGetData(UAVObjHandle h, void *out) { return UAVObjGetInstanceData(h, 0, out); }
int32_t UAVObjSetInstanceData(UAVObjHandle h, uint16_t instance, const void *in) {
    CHECK(h); struct object *o = h; CHECK(instance < o->instances);
#ifdef TEST_ATTITUDE
    if (!in_registration && !in_worker && fail_init_write && o->id == ATTITUDESTATE_OBJID) return -1;
#endif
    memcpy(o->data[instance], in, o->size); return 0;
}
int32_t UAVObjSetData(UAVObjHandle h, const void *in) { return UAVObjSetInstanceData(h, 0, in); }
int32_t UAVObjGetDataField(UAVObjHandle h, void *out, uint32_t offset, uint32_t size) {
    if (!h) return -1;
    struct object *o = h; CHECK(offset + size <= o->size);
    if (deny_read(o)) return -1;
    memcpy(out, o->data[0] + offset, size); return 0;
}
int32_t UAVObjSetDataField(UAVObjHandle h, const void *in, uint32_t offset, uint32_t size) {
    CHECK(h); struct object *o = h; CHECK(offset + size <= o->size);
    memcpy(o->data[0] + offset, in, size); return 0;
}
uint16_t UAVObjGetNumInstances(UAVObjHandle h) { CHECK(h); return ((struct object *)h)->instances; }
uint16_t UAVObjCreateInstance(UAVObjHandle h, UAVObjInitializeCallback cb) {
    CHECK(h && !in_worker); struct object *o = h; ++instance_calls;
    /* Pinned UAVObjCreateInstance can return the intended nonzero instance ID
     * when allocation fails. The consumer must verify actual count growth. */
    bool fail = instance_calls == (unsigned)fail_instance;
    if (fail && !fail_instance_grown) return fail_instance_zero ? 0 : o->instances;
    CHECK(o->instances < 3); unsigned instance = o->instances++;
    in_registration = true; cb(h, instance); in_registration = false;
    return fail ? 0 : instance;
}
int32_t UAVObjSetMetadata(UAVObjHandle h, const UAVObjMetadata *m) { CHECK(h); ((struct object *)h)->metadata = *m; return 0; }
int32_t UAVObjGetMetadata(UAVObjHandle h, UAVObjMetadata *m) { CHECK(h); *m = ((struct object *)h)->metadata; return 0; }
void UAVObjSetAccess(UAVObjMetadata *m, UAVObjAccessType a) { m->flags = (m->flags & ~1) | a; }
int8_t UAVObjReadOnly(UAVObjHandle h) { return 0; }
int32_t UAVObjConnectCallback(UAVObjHandle h, UAVObjEventCallback cb, uint8_t mask) {
    CHECK(h && cb); ++connections;
    for (unsigned i = 0; i < subscription_count; ++i) {
        if (subscriptions[i].obj == h && subscriptions[i].cb == cb) { subscriptions[i].mask = mask; return 0; }
    }
    if (connections == (unsigned)fail_callback) return -1;
    CHECK(subscription_count < 2);
    subscriptions[subscription_count++] = (struct subscription){ h, cb, mask }; return 0;
}
static void check_subscriptions(unsigned count) {
    const struct subscription expected[] = {
#ifdef TEST_ATTITUDE
        { AttitudeSettingsHandle(), settingsUpdatedCb, EV_MASK_ALL_UPDATES },
        { AccelGyroSettingsHandle(), settingsUpdatedCb, EV_MASK_ALL_UPDATES },
#else
        { VtolPathFollowerSettingsHandle(), SettingsUpdatedCb, EV_MASK_ALL_UPDATES },
        { SystemSettingsHandle(), SettingsUpdatedCb, EV_MASK_ALL_UPDATES },
#endif
    };
    CHECK(subscription_count == count && count <= 2);
    for (unsigned i = 0; i < count; ++i) {
        CHECK(subscriptions[i].obj == expected[i].obj && subscriptions[i].cb == expected[i].cb);
        CHECK(subscriptions[i].mask == expected[i].mask);
    }
}
void *pios_malloc(size_t size) {
    ++allocations; CHECK(!in_worker && size == sizeof(PIOS_SENSORS_3Axis_SensorsWithTemp) + 2 * sizeof(Vector3i16));
    return fail_allocation ? NULL : calloc(1, size);
}
void pios_free(void *p) { free(p); }
static void run_worker(void) {
    CHECK(worker_live && worker_entry && !in_worker); in_worker = true;
    if (!setjmp(worker_exit)) { worker_entry(NULL); CHECK(!"worker returned unexpectedly"); }
    in_worker = false;
}
int xTaskCreate(void (*entry)(void *), const char *name, unsigned size, void *p, unsigned priority, xTaskHandle *h) {
    ++creates; CHECK(!strcmp(name, INPUT_NAME) && size == INPUT_STACK_WORDS && priority == 3 && p == NULL);
    if (fail_task) return 0;
    worker_live = true; worker_entry = entry;
    if (h) { ++output_handle_requests; *h = &task_token; }
    if (early) run_worker();
    return pdPASS;
}
xTaskHandle xTaskGetCurrentTaskHandle(void) { CHECK(in_worker); return &task_token; }
int32_t PIOS_TASK_MONITOR_RegisterTask(uint16_t id, xTaskHandle h) {
    ++monitor_calls; CHECK(in_worker && worker_live && h == &task_token && id == INPUT_MONITOR);
    if (fail_monitor) return -1;
    monitored = true; return 0;
}
int32_t PIOS_TASK_MONITOR_UnregisterTask(uint16_t id) {
    ++unregisters; CHECK(in_worker && worker_live && monitored && id == INPUT_MONITOR && shutdowns == 1);
    if (fail_unregister) return -1;
    monitored = false; return 0;
}
void vTaskDelete(xTaskHandle h) {
    CHECK(h == NULL && in_worker && worker_live && !monitored && shutdowns == 1 && fault_alarms == 1);
    worker_live = false; ++task_deletes; longjmp(worker_exit, 1);
}
void vTaskDelay(portTickType delay) {
    CHECK(in_worker && worker_live && monitored && shutdowns == 1 && fault_alarms == 1 && delay == portMAX_DELAY);
    /* A delay can return. Require a second safe wait rather than hiding an
     * eventual fall-through into deletion of the still-monitored task. */
    if (++parked == 1) return;
    CHECK(parked == 2); longjmp(worker_exit, 1);
}
void vTaskDelayUntil(portTickType *t, portTickType delay) {
    CHECK(in_worker && monitored && delay == 20); check_initial_settings();
    ++loop_waits; longjmp(worker_exit, 1);
}
bool PIOS_WDG_RegisterFlag(uint16_t flag) {
    ++watchdog_calls; CHECK(!in_worker && flag == INPUT_WDG && creates == 0); return !fail_watchdog;
}
bool PIOS_WDG_UpdateFlag(uint16_t flag) { CHECK(in_worker && monitored && flag == INPUT_WDG); return true; }
portTickType xTaskGetTickCount(void) { return 0; }
uint32_t PIOS_DELAY_GetRaw(void) { return 0; }
uint32_t PIOS_DELAY_DiffuS(uint32_t before) { return 0; }
int xQueueReceive(xQueueHandle queue, void *out, unsigned timeout) {
    CHECK(in_worker && monitored && queue == &sensor_queue_token && out && timeout == 10);
    CHECK(sensor_tests == 1 && !fail_test && !fail_sensor_queue);
    check_initial_settings();
    ++loop_waits; longjmp(worker_exit, 1);
}
int32_t PIOS_RCVR_Read(uint32_t id, uint8_t channel) { CHECK(!"receiver loop ran past first wait"); return -1; }
int32_t AlarmsSet(SystemAlarmsAlarmElem alarm, SystemAlarmsAlarmOptions severity) {
    if (alarm == SYSTEMALARMS_ALARM_BOOTFAULT) { CHECK(severity == SYSTEMALARMS_ALARM_CRITICAL); ++fault_alarms; }
    alarms[alarm] = severity; return 0;
}
int32_t AlarmsClear(SystemAlarmsAlarmElem alarm) { alarms[alarm] = SYSTEMALARMS_ALARM_OK; return 0; }
SystemAlarmsAlarmOptions AlarmsGet(SystemAlarmsAlarmElem alarm) { return alarms[alarm]; }
void PIOS_LiteWing_BrushedPWM_Shutdown(void) { ++shutdowns; }
FrameType_t GetCurrentFrameType(void) { CHECK(in_worker && monitored); ++frame_queries; return FRAME_TYPE_CUSTOM; }
void PIOS_NOTIFY_StartNotification(pios_notify_notification notification, pios_notify_priority priority) {}
static bool sensor_test(uintptr_t context) { CHECK(in_worker && monitored && context == 0); ++sensor_tests; return !fail_test; }
static QueueHandle_t sensor_queue(uintptr_t context) { CHECK(in_worker && monitored && context == 0); return fail_sensor_queue ? NULL : &sensor_queue_token; }
static void sensor_scale(float *scale, uint8_t count, uintptr_t context) { CHECK(in_worker && monitored && count == 2 && context == 0); ++scales; scale[0] = 2.0f; scale[1] = 3.0f; }
const PIOS_SENSORS_Driver PIOS_ICM20602_Driver = { .test = sensor_test, .get_queue = sensor_queue, .get_scale = sensor_scale };

#define LATER(Name) int32_t Name##Initialize(void) { ++later_inits; return 0; } \
    int32_t Name##Start(void) { ++later_starts; return 0; }
#ifdef TEST_ATTITUDE
LATER(Stabilization) LATER(Actuator) LATER(Receiver)
#else
int32_t AttitudeInitialize(void) { return 0; }
int32_t AttitudeStart(void) { return 0; }
int32_t StabilizationInitialize(void) { return 0; }
int32_t StabilizationStart(void) { return 0; }
int32_t ActuatorInitialize(void) { return 0; }
int32_t ActuatorStart(void) { return 0; }
#endif
LATER(ManualControl) LATER(Telemetry)
int32_t LiteWingBatteryInitialize(void) { return 0; }
int32_t LiteWingBatteryStart(void) { return 0; }

static unsigned resources_touched(void) { return registrations + connections + allocations + instance_calls; }
int main(int argc, char **argv) {
    CHECK(argc == 2); const char *s = argv[1];
    if (!strcmp(s, "stack-bytes")) { printf("%u\n", INPUT_STACK_WORDS * 4u); return 0; }
    if (!strncmp(s, "object-", 7)) fail_object = atoi(s + 7);
    if (!strncmp(s, "callback-", 9)) fail_callback = atoi(s + 9);
    if (!strcmp(s, "instance-zero-grown")) { fail_instance = 1; fail_instance_grown = true; }
    else if (!strncmp(s, "instance-zero-", 14)) { fail_instance = atoi(s + 14); fail_instance_zero = true; }
    else if (!strncmp(s, "instance-", 9)) fail_instance = atoi(s + 9);
    fail_task = !strcmp(s, "task"); fail_watchdog = !strcmp(s, "watchdog");
    fail_monitor = !strncmp(s, "monitor-", 8); early = strstr(s, "early") != NULL;
    fail_test = !strncmp(s, "sensor-test", 11); fail_sensor_queue = !strncmp(s, "sensor-queue", 12);
    fail_unregister = strstr(s, "park") != NULL;
    fail_command_read = !strncmp(s, "runtime-command", 15); fail_flight_read = !strncmp(s, "runtime-flight", 14);
    fail_allocation = !strcmp(s, "allocation"); fail_init_read = !strcmp(s, "init-read"); fail_init_write = !strcmp(s, "init-write");
    if (!strcmp(s, "premature")) CHECK(INPUT_START() != 0 && creates == 0 && watchdog_calls == 0);
    if (!strcmp(s, "existing")) {
#ifdef TEST_ATTITUDE
        CHECK(AttitudeStateInitialize() == 0 && AttitudeSettingsInitialize() == 0 && AccelGyroSettingsInitialize() == 0);
        CHECK(AccelStateInitialize() == 0 && GyroStateInitialize() == 0);
#else
        CHECK(AccessoryDesiredInitialize() == 0 && ManualControlCommandInitialize() == 0 && ReceiverActivityInitialize() == 0);
        CHECK(ManualControlSettingsInitialize() == 0 && StabilizationSettingsInitialize() == 0);
        CHECK(VtolPathFollowerSettingsInitialize() == 0 && SystemSettingsInitialize() == 0);
        CHECK(AccessoryDesiredCreateInstance() == 1 && AccessoryDesiredCreateInstance() == 2);
#endif
    }
    int32_t rc = PIOS_LiteWing_ModulesInitialize();
    bool init_failure = fail_object || fail_callback || fail_allocation || fail_init_read || fail_init_write || fail_instance;
    if (init_failure) {
        CHECK(rc != 0 && later_inits == 0 && creates == 0 && !worker_live);
        CHECK(PIOS_LiteWing_ModulesStart() != 0 && creates == 0 && later_starts == 0);
        CHECK(INPUT_START() != 0 && watchdog_calls == 0);
        unsigned before = resources_touched(); CHECK(INPUT_INIT() != 0 && resources_touched() == before);
        if (fail_callback) check_subscriptions(fail_callback - 1);
        return 0;
    }
    CHECK(rc == 0 && later_inits == LATER_MODULES && registrations == INPUT_OBJECTS);
    check_subscriptions(2);
#ifdef TEST_ATTITUDE
    CHECK(allocations == 1 && mpu6000_data);
    AttitudeStateData attitude; CHECK(AttitudeStateGet(&attitude) == 0);
    CHECK(attitude.q1 == 1.0f && attitude.q2 == 0.0f && attitude.q3 == 0.0f && attitude.q4 == 0.0f);
#else
    CHECK(UAVObjGetNumInstances(AccessoryDesiredHandle()) == 3 && instance_calls == 2);
#endif
    if (!FlightStatusHandle()) CHECK(FlightStatusInitialize() == 0);
    if (!ManualControlCommandHandle()) CHECK(ManualControlCommandInitialize() == 0);
    /* No event dispatcher is simulated here: only the worker's explicit
     * initial callback can apply these distinguishable settings. */
#ifdef TEST_ATTITUDE
    AttitudeSettingsData seeded_attitude; CHECK(AttitudeSettingsGet(&seeded_attitude) == 0);
    seeded_attitude.BoardRotation.Roll = seeded_attitude.BoardRotation.Pitch = 0;
    seeded_attitude.BoardRotation.Yaw = 90;
    CHECK(AttitudeSettingsSet(&seeded_attitude) == 0);
    AccelGyroSettingsData seeded_scales; CHECK(AccelGyroSettingsGet(&seeded_scales) == 0);
    seeded_scales.gyro_scale = (AccelGyroSettingsgyro_scaleData){ 1.5f, 2.0f, 2.5f };
    seeded_scales.accel_scale = (AccelGyroSettingsaccel_scaleData){ 1.25f, 1.5f, 1.75f };
    CHECK(AccelGyroSettingsSet(&seeded_scales) == 0);
#else
    uint8_t custom_as = VTOLPATHFOLLOWERSETTINGS_TREATCUSTOMCRAFTAS_GROUND;
    VtolPathFollowerSettingsTreatCustomCraftAsSet(&custom_as);
#endif
    if (!strcmp(s, "repeat")) { unsigned before = resources_touched(); CHECK(INPUT_INIT() != 0 && resources_touched() == before); }
    rc = PIOS_LiteWing_ModulesStart();
    if (fail_task || fail_watchdog) {
        CHECK(rc != 0 && later_starts == 0 && creates == (unsigned)!fail_watchdog);
        CHECK(!worker_live && monitor_calls == 0);
    } else {
        CHECK(rc == 0 && later_starts == LATER_MODULES && creates == 1 && watchdog_calls == 1 && output_handle_requests == 0);
        if (!early) { CHECK(monitor_calls == 0 && loop_waits == 0); run_worker(); }
        CHECK(monitor_calls == 1);
        bool worker_failure = fail_monitor || fail_test || fail_sensor_queue || fail_command_read || fail_flight_read;
        if (worker_failure) {
            CHECK(shutdowns == 1 && fault_alarms == 1 && loop_waits == 0);
            CHECK(unregisters == (unsigned)!fail_monitor);
            if (fail_unregister) CHECK(worker_live && monitored && parked == 2 && task_deletes == 0);
            else CHECK(!worker_live && !monitored && parked == 0 && task_deletes == 1);
        } else CHECK(worker_live && monitored && loop_waits == 1 && task_deletes == 0 && shutdowns == 0 && fault_alarms == 0);
    }
    unsigned before = creates + watchdog_calls;
    CHECK(INPUT_START() != 0 && creates + watchdog_calls == before);
    return 0;
}
