/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Whole generated inner loop with real UAVObjects and controlled scheduler. */
#include <openpilot.h>
#include <stdio.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL: %s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#include MODULE_SOURCE

struct object { uint32_t id, size; unsigned char data[2048]; UAVObjMetadata metadata; };
static struct object objects[12];
static unsigned object_count, registrations, scheduler_creates, callback_connects, schedules;
static int fail_object;
static bool fail_scheduler, fail_callback, fail_schedule;
static int callback_token;
static DelayedCallback scheduled_callback;
static UAVObjEventCallback gyro_callback;
StabilizationData stabSettings;

UAVObjHandle UAVObjGetByID(uint32_t id)
{
    for (unsigned i = 0; i < object_count; ++i) if (objects[i].id == id) return &objects[i];
    return NULL;
}

UAVObjHandle UAVObjRegister(uint32_t id, bool single, bool settings, bool priority,
                           uint32_t size, UAVObjInitializeCallback cb)
{
    if (++registrations == (unsigned)fail_object) return NULL;
    CHECK(object_count < 12 && size <= sizeof(objects[0].data) && !UAVObjGetByID(id));
    struct object *object = &objects[object_count++];
    object->id = id; object->size = size; cb(object, 0); return object;
}

int32_t UAVObjGetData(UAVObjHandle h, void *out)
{
    if (!h) return -1;
    struct object *object = h; memcpy(out, object->data, object->size); return 0;
}

int32_t UAVObjSetData(UAVObjHandle h, const void *in)
{
    if (!h) return -1;
    struct object *object = h; memcpy(object->data, in, object->size); return 0;
}

int32_t UAVObjGetInstanceData(UAVObjHandle h, uint16_t instance, void *out)
{ CHECK(instance == 0); return UAVObjGetData(h, out); }
int32_t UAVObjSetInstanceData(UAVObjHandle h, uint16_t instance, const void *in)
{ CHECK(instance == 0); return UAVObjSetData(h, in); }
int32_t UAVObjGetDataField(UAVObjHandle h, void *out, uint32_t offset, uint32_t size)
{
    if (!h) return -1;
    struct object *object = h; CHECK(offset + size <= object->size);
    memcpy(out, object->data + offset, size); return 0;
}
int32_t UAVObjSetDataField(UAVObjHandle h, const void *in, uint32_t offset, uint32_t size)
{
    if (!h) return -1;
    struct object *object = h; CHECK(offset + size <= object->size);
    memcpy(object->data + offset, in, size); return 0;
}
int32_t UAVObjSetMetadata(UAVObjHandle h, const UAVObjMetadata *metadata)
{ CHECK(h); ((struct object *)h)->metadata = *metadata; return 0; }

int32_t UAVObjConnectCallback(UAVObjHandle h, UAVObjEventCallback cb, uint8_t mask)
{
    ++callback_connects;
    CHECK(h == GyroStateHandle() && cb && mask == EV_MASK_ALL_UPDATES && !gyro_callback);
    if (fail_callback) return -1;
    gyro_callback = cb; return 0;
}

DelayedCallbackInfo *PIOS_CALLBACKSCHEDULER_Create(DelayedCallback cb,
    DelayedCallbackPriority priority, DelayedCallbackPriorityTask task,
    int16_t id, uint32_t stack)
{
    ++scheduler_creates;
    CHECK(cb && priority == CALLBACK_PRIORITY_CRITICAL && task == CALLBACK_TASK_FLIGHTCONTROL);
    CHECK(id == CALLBACKINFO_RUNNING_STABILIZATION1 && stack == PIOS_STABILIZATION_STACK_SIZE);
    if (fail_scheduler) return NULL;
    scheduled_callback = cb; return (DelayedCallbackInfo *)&callback_token;
}

int32_t PIOS_CALLBACKSCHEDULER_Schedule(DelayedCallbackInfo *handle, int32_t milliseconds,
                                        DelayedCallbackUpdateMode mode)
{
    ++schedules;
    CHECK(handle == (DelayedCallbackInfo *)&callback_token && scheduled_callback);
    CHECK(milliseconds == FAILSAFE_TIMEOUT_MS && mode == CALLBACK_UPDATEMODE_LATER);
    return fail_schedule ? 0 : 1;
}

int32_t PIOS_CALLBACKSCHEDULER_Dispatch(DelayedCallbackInfo *handle)
{ CHECK(handle == (DelayedCallbackInfo *)&callback_token); return 1; }
bool PIOS_WDG_UpdateFlag(uint16_t flag) { CHECK(flag == PIOS_WDG_STABILIZATION); return true; }
portTickType xTaskGetTickCount(void) { return 0; }
uint32_t PIOS_DELAY_GetRaw(void) { return 0; }
uint32_t PIOS_DELAY_DiffuS(uint32_t before) { (void)before; return 2000; }
int32_t AlarmsSet(SystemAlarmsAlarmElem alarm, SystemAlarmsAlarmOptions severity)
{ (void)alarm; (void)severity; return 0; }
int32_t AlarmsClear(SystemAlarmsAlarmElem alarm) { (void)alarm; return 0; }
int stabilization_virtual_flybar(float gyro, float command, float *output, float dt,
                                 bool reinit, uint32_t axis, StabilizationSettingsData *settings)
{ (void)gyro; (void)command; (void)output; (void)dt; (void)reinit; (void)axis; (void)settings; return 0; }
int stabilization_relay_rate(float error, float *output, int axis, bool reinit)
{ (void)error; (void)output; (void)axis; (void)reinit; return 0; }
float cruisecontrol_apply_factor(float raw) { return raw; }

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    const char *scenario = argv[1];
    if (!strncmp(scenario, "object-", 7)) fail_object = atoi(scenario + 7);
    fail_scheduler = !strcmp(scenario, "scheduler");
    fail_callback = !strcmp(scenario, "callback");
    fail_schedule = !strcmp(scenario, "schedule");
    if (!strcmp(scenario, "existing")) {
        CHECK(RateDesiredInitialize() == 0 && ActuatorDesiredInitialize() == 0);
        CHECK(GyroStateInitialize() == 0 && StabilizationStatusInitialize() == 0);
        CHECK(FlightStatusInitialize() == 0 && ManualControlCommandInitialize() == 0);
        CHECK(StabilizationDesiredInitialize() == 0);
    }
    unsigned before = registrations;
    bool should_fail = fail_object || fail_scheduler || fail_callback || fail_schedule;
    int32_t result = PIOS_LiteWing_StabilizationInnerloopInitialize();
    CHECK((result != 0) == should_fail);
    CHECK(registrations == before + (fail_object ? (unsigned)fail_object :
          !strcmp(scenario, "existing") ? 0U : 7U));
    CHECK(scheduler_creates == (unsigned)(!fail_object));
    CHECK(callback_connects == (unsigned)(!fail_object && !fail_scheduler));
    CHECK(schedules == (unsigned)(!fail_object && !fail_scheduler && !fail_callback));
    CHECK((gyro_callback != NULL) == (!fail_object && !fail_scheduler && !fail_callback));
    unsigned effects = registrations + scheduler_creates + callback_connects + schedules;
    CHECK(PIOS_LiteWing_StabilizationInnerloopInitialize() != 0);
    CHECK(registrations + scheduler_creates + callback_connects + schedules == effects);
    return 0;
}
