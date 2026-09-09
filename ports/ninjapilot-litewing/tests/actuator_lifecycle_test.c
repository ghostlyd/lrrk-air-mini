/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Whole real module + generated objects. Controlled OS/store boundaries;
 * early/deferred task execution is deterministic, not an RTOS simulation. */
#include <openpilot.h>
#include <setjmp.h>
#include <stdio.h>
#include <pios_litewing_modules.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL: %s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#ifdef __clang__
#pragma clang diagnostic ignored "-Wparentheses-equality"
#endif
#include MODULE_SOURCE

struct object { uint32_t id, size; unsigned char data[2048]; UAVObjMetadata metadata; };
static struct object objects[16];
static unsigned object_count, registrations, callbacks, connects, creates, deletes;
static unsigned task_creates, monitor_calls, task_deletes, watchdog_calls, output_setups;
static unsigned fault_alarms, shutdowns, later_inits, later_starts;
static int fail_object, fail_callback;
static bool fail_queue, fail_connect, fail_task, fail_watchdog, fail_monitor;
static bool queue_live, queue_published, worker_live, monitored, in_worker, early;
static int queue_token, worker_token;
static void (*worker_entry)(void *);
static jmp_buf worker_exit;
static SystemAlarmsAlarmOptions alarms[SYSTEMALARMS_ALARM_NUMELEM];

UAVObjHandle UAVObjGetByID(uint32_t id) {
    for (unsigned i = 0; i < object_count; ++i) if (objects[i].id == id) return &objects[i];
    return NULL;
}
UAVObjHandle UAVObjRegister(uint32_t id, bool single, bool settings, bool priority,
                           uint32_t size, UAVObjInitializeCallback cb) {
    if (++registrations == (unsigned)fail_object) return NULL;
    CHECK(object_count < 16 && size <= 2048 && !UAVObjGetByID(id));
    struct object *obj = &objects[object_count++]; obj->id = id; obj->size = size;
    cb(obj, 0); return obj;
}
int32_t UAVObjGetData(UAVObjHandle h, void *out) {
    if (!h) return -1;
    struct object *o = h; memcpy(out, o->data, o->size); return 0;
}
int32_t UAVObjSetData(UAVObjHandle h, const void *in) {
    CHECK(h); struct object *o = h; memcpy(o->data, in, o->size); return 0;
}
int32_t UAVObjGetDataField(UAVObjHandle h, void *out, uint32_t offset, uint32_t size) {
    if (!h) return -1;
    struct object *o = h; CHECK(offset + size <= o->size); memcpy(out, o->data + offset, size); return 0;
}
int32_t UAVObjSetDataField(UAVObjHandle h, const void *in, uint32_t offset, uint32_t size) {
    CHECK(h); struct object *o = h; CHECK(offset + size <= o->size); memcpy(o->data + offset, in, size); return 0;
}
int32_t UAVObjGetInstanceData(UAVObjHandle h, uint16_t instance, void *out) { return UAVObjGetData(h, out); }
int32_t UAVObjSetInstanceData(UAVObjHandle h, uint16_t instance, const void *in) { return UAVObjSetData(h, in); }
uint16_t UAVObjCreateInstance(UAVObjHandle h, UAVObjInitializeCallback cb) { return 1; }
int32_t UAVObjSetMetadata(UAVObjHandle h, const UAVObjMetadata *m) { CHECK(h); ((struct object *)h)->metadata = *m; return 0; }
int32_t UAVObjGetMetadata(UAVObjHandle h, UAVObjMetadata *m) { CHECK(h); *m = ((struct object *)h)->metadata; return 0; }
void UAVObjSetAccess(UAVObjMetadata *m, UAVObjAccessType a) { m->flags = (m->flags & ~1) | a; }
int8_t UAVObjReadOnly(UAVObjHandle h) { return 0; }
int32_t UAVObjConnectCallback(UAVObjHandle h, UAVObjEventCallback cb, uint8_t mask) {
    CHECK(h && cb); return ++callbacks == (unsigned)fail_callback ? -1 : 0;
}
int32_t UAVObjConnectQueue(UAVObjHandle h, xQueueHandle q, uint8_t mask) {
    ++connects; CHECK(h && q == &queue_token && queue_live && !queue_published);
    if (fail_connect) return -1;
    queue_published = true; return 0;
}
xQueueHandle xQueueCreate(unsigned count, unsigned size) {
    ++creates; CHECK(count == 2 && size == sizeof(UAVObjEvent) && !queue_live);
    if (fail_queue) return NULL;
    queue_live = true; return &queue_token;
}
void vQueueDelete(xQueueHandle q) { CHECK(q == &queue_token && queue_live && !queue_published); queue_live = false; ++deletes; }
static void run_worker(void) {
    CHECK(worker_live && worker_entry && !in_worker); in_worker = true;
    if (!setjmp(worker_exit)) { worker_entry(NULL); CHECK(!"worker returned unexpectedly"); }
    in_worker = false;
}
int xTaskCreate(void (*entry)(void *), const char *name, unsigned size, void *p, unsigned priority, xTaskHandle *h) {
    ++task_creates; CHECK(!strcmp(name, "Actuator") && size == 328 && priority == 4 && p == NULL);
    if (fail_task) return 0;
    worker_live = true; worker_entry = entry;
    if (h) *h = &worker_token;
    if (early) run_worker();
    return pdPASS;
}
xTaskHandle xTaskGetCurrentTaskHandle(void) { CHECK(in_worker); return &worker_token; }
int32_t PIOS_TASK_MONITOR_RegisterTask(uint16_t id, xTaskHandle h) {
    ++monitor_calls; CHECK(in_worker && worker_live && h == &worker_token && id == TASKINFO_RUNNING_ACTUATOR);
    if (fail_monitor) return -1;
    monitored = true; return 0;
}
void vTaskDelete(xTaskHandle h) {
    CHECK(h == NULL && in_worker && worker_live && !monitored);
    worker_live = false; ++task_deletes; longjmp(worker_exit, 1);
}
bool PIOS_WDG_RegisterFlag(uint16_t flag) {
    ++watchdog_calls; CHECK(!in_worker && flag == PIOS_WDG_ACTUATOR && task_creates == 0);
    return !fail_watchdog;
}
bool PIOS_WDG_UpdateFlag(uint16_t flag) { CHECK(in_worker && monitored && flag == PIOS_WDG_ACTUATOR); return true; }
int xQueueReceive(xQueueHandle q, void *ev, unsigned timeout) {
    CHECK(in_worker && monitored && q == &queue_token && queue_published && timeout == 100);
    longjmp(worker_exit, 1);
}
portTickType xTaskGetTickCount(void) { return 0; }
int32_t AlarmsSet(SystemAlarmsAlarmElem alarm, SystemAlarmsAlarmOptions severity) {
    if (alarm == SYSTEMALARMS_ALARM_BOOTFAULT) { CHECK(severity == SYSTEMALARMS_ALARM_CRITICAL); ++fault_alarms; }
    alarms[alarm] = severity;
    return 0;
}
int32_t AlarmsClear(SystemAlarmsAlarmElem alarm) { alarms[alarm] = SYSTEMALARMS_ALARM_OK; return 0; }
SystemAlarmsAlarmOptions AlarmsGet(SystemAlarmsAlarmElem alarm) { return alarms[alarm]; }
void PIOS_LiteWing_BrushedPWM_Shutdown(void) { ++shutdowns; }
FrameType_t GetCurrentFrameType(void) { return FRAME_TYPE_MULTIROTOR; }
static void output_setup(void) { CHECK(in_worker && monitored && !fail_monitor); ++output_setups; }
void PIOS_Servo_Update(void) { output_setup(); }
void PIOS_Servo_Set(uint8_t channel, uint16_t value) { output_setup(); }
void PIOS_Servo_SetBankMode(uint8_t bank, int mode) { output_setup(); }
void PIOS_Servo_SetHz(const uint16_t *hz, const uint32_t *clock, uint8_t count) { output_setup(); }
uint8_t PIOS_Servo_GetPinBank(uint8_t pin) { return 0; }

int32_t AttitudeInitialize(void) { return 0; }
int32_t StabilizationInitialize(void) { return 0; }
int32_t AttitudeStart(void) { return 0; }
int32_t StabilizationStart(void) { return 0; }
#define LATER(Name) int32_t Name##Initialize(void) { ++later_inits; return 0; } \
    int32_t Name##Start(void) { ++later_starts; return 0; }
LATER(Receiver) LATER(ManualControl) LATER(Telemetry)

int main(int argc, char **argv) {
    CHECK(argc == 2); const char *s = argv[1];
    if (!strncmp(s, "object-", 7)) fail_object = atoi(s + 7);
    if (!strncmp(s, "callback-", 9)) fail_callback = atoi(s + 9);
    fail_queue = !strcmp(s, "queue"); fail_connect = !strcmp(s, "connection");
    fail_task = !strcmp(s, "task"); fail_watchdog = !strcmp(s, "watchdog");
    fail_monitor = !strncmp(s, "monitor-", 8); early = strstr(s, "early") != NULL;
    if (!strcmp(s, "premature")) {
        CHECK(ActuatorStart() != 0 && task_creates == 0 && watchdog_calls == 0);
    }
    if (!strcmp(s, "existing")) {
        CHECK(ActuatorSettingsInitialize() == 0 && MixerSettingsInitialize() == 0);
        CHECK(ActuatorDesiredInitialize() == 0 && AccessoryDesiredInitialize() == 0);
        CHECK(ActuatorCommandInitialize() == 0 && VtolPathFollowerSettingsInitialize() == 0 && SystemSettingsInitialize() == 0);
    }
    bool init_fail = fail_object || fail_callback || fail_queue || fail_connect;
    int32_t rc = PIOS_LiteWing_ModulesInitialize();
    if (init_fail) {
        CHECK(rc != 0 && later_inits == 0 && task_creates == 0 && !queue_live);
        CHECK(PIOS_LiteWing_ModulesStart() != 0 && later_starts == 0);
        CHECK(connects == (unsigned)fail_connect && deletes == (unsigned)fail_connect);
        CHECK(ActuatorStart() != 0 && task_creates == 0);
        unsigned before = registrations + callbacks + creates;
        CHECK(ActuatorInitialize() != 0 && registrations + callbacks + creates == before);
        return 0;
    }
    CHECK(rc == 0 && later_inits == 3 && registrations == 7 && callbacks == 4);
    CHECK(queue_live && queue_published && connects == 1 && creates == 1 && deletes == 0);
    CHECK(FlightStatusInitialize() == 0 && ManualControlCommandInitialize() == 0);
    if (!strcmp(s, "repeat")) {
        unsigned before = registrations + callbacks + creates;
        CHECK(ActuatorInitialize() != 0 && registrations + callbacks + creates == before);
    }
    rc = PIOS_LiteWing_ModulesStart();
    if (fail_task || fail_watchdog) {
        CHECK(rc != 0 && later_starts == 0 && task_creates == (unsigned)!fail_watchdog);
        CHECK(!worker_live && monitor_calls == 0 && queue_live && queue_published && deletes == 0);
    } else {
        CHECK(rc == 0 && later_starts == 3 && task_creates == 1 && watchdog_calls == 1);
        if (!early) { CHECK(monitor_calls == 0 && output_setups == 0); run_worker(); }
        CHECK(monitor_calls == 1 && queue_live && queue_published && deletes == 0);
        if (fail_monitor) {
            CHECK(!worker_live && !monitored && task_deletes == 1 && output_setups == 0);
            CHECK(shutdowns == 1 && fault_alarms == 1);
        } else {
            CHECK(worker_live && monitored && task_deletes == 0 && output_setups > 0);
            CHECK(shutdowns == 0 && fault_alarms == 0);
        }
    }
    unsigned before = task_creates + watchdog_calls;
    CHECK(ActuatorStart() != 0 && task_creates + watchdog_calls == before);
    return 0;
}
