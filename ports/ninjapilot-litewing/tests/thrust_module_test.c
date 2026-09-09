/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Run the complete pinned/adapted task against an in-memory object store.
 * No serial, network, threads, or physical output APIs are used. */
#include <openpilot.h>
#include <setjmp.h>
#include <stdio.h>
#include <accessorydesired.h>
#include <actuatordesired.h>
#include <actuatorcommand.h>
#include <actuatorsettings.h>
#include <flightstatus.h>
#include <manualcontrolcommand.h>
#include <manualcontrolsettings.h>
#include <mixersettings.h>
#include <systemsettings.h>
#include <flighttelemetrystats.h>
#include <receiveractivity.h>
#ifdef __clang__
#pragma clang diagnostic ignored "-Wparentheses-equality"
#endif
#include MODULE_SOURCE

struct object { uint32_t id, size; unsigned char data[2048]; UAVObjMetadata metadata; };
static struct object objects[16];
static unsigned object_count;
static int fail_thrust_read;
static jmp_buf stop_task;
static unsigned iterations, iteration_limit = 1;
static unsigned ticks;
static const char *scenario;
static bool deny_publication, shutdown_latched;
static uint16_t first_recovery_output;
static bool powered_recovery;
static SystemAlarmsAlarmOptions alarms[SYSTEMALARMS_ALARM_NUMELEM];
static uint16_t hardware_output[ACTUATORCOMMAND_CHANNEL_NUMELEM];
uint32_t pios_rcvr_group_map[8] = { 1, 1, 1, 1, 1, 1, 1, 1 };

UAVObjHandle UAVObjGetByID(uint32_t id) {
    for (unsigned i = 0; i < object_count; ++i) if (objects[i].id == id) return &objects[i];
    return NULL;
}
UAVObjHandle UAVObjRegister(uint32_t id, bool single, bool settings, bool priority,
                           uint32_t size, UAVObjInitializeCallback cb) {
    assert(object_count < 16 && size <= sizeof(objects[0].data));
    struct object *obj = &objects[object_count++]; obj->id = id; obj->size = size;
    cb(obj, 0); return obj;
}
int32_t UAVObjGetData(UAVObjHandle h, void *out) {
    if (!h) return -1;
    struct object *obj = h; memcpy(out, obj->data, obj->size); return 0;
}
int32_t UAVObjSetData(UAVObjHandle h, const void *in) {
    assert(h); struct object *obj = h;
    if (deny_publication && obj->id == MANUALCONTROLCOMMAND_OBJID) return -1;
    memcpy(obj->data, in, obj->size); return 0;
}
int32_t UAVObjGetDataField(UAVObjHandle h, void *out, uint32_t offset, uint32_t size) {
    if (!h) return -1;
    struct object *obj = h; assert(offset + size <= obj->size);
    if (obj->id == SYSTEMSETTINGS_OBJID && offset == 45) {
        assert(size == 1);
        if (fail_thrust_read) {
            if (fail_thrust_read == 2) memcpy(out, obj->data + offset, size);
            return -1;
        }
    }
    memcpy(out, obj->data + offset, size); return 0;
}
int32_t UAVObjSetDataField(UAVObjHandle h, const void *in, uint32_t offset, uint32_t size) {
    assert(h); struct object *obj = h; assert(offset + size <= obj->size);
    memcpy(obj->data + offset, in, size); return 0;
}
int32_t UAVObjGetInstanceData(UAVObjHandle h, uint16_t instance, void *out) { return UAVObjGetData(h, out); }
int32_t UAVObjSetInstanceData(UAVObjHandle h, uint16_t instance, const void *in) { return UAVObjSetData(h, in); }
uint16_t UAVObjCreateInstance(UAVObjHandle h, UAVObjInitializeCallback cb) { return 1; }
int32_t UAVObjSetMetadata(UAVObjHandle h, const UAVObjMetadata *m) { ((struct object *)h)->metadata = *m; return 0; }
int32_t UAVObjGetMetadata(UAVObjHandle h, UAVObjMetadata *m) { *m = ((struct object *)h)->metadata; return 0; }
void UAVObjSetAccess(UAVObjMetadata *m, UAVObjAccessType a) { m->flags = (m->flags & ~1) | a; }
int8_t UAVObjReadOnly(UAVObjHandle h) { return deny_publication && ((struct object *)h)->id == MANUALCONTROLCOMMAND_OBJID; }
int32_t UAVObjConnectCallback(UAVObjHandle h, UAVObjEventCallback cb, uint8_t mask) { return 0; }
int32_t UAVObjConnectQueue(UAVObjHandle h, xQueueHandle q, uint8_t mask) { return 0; }
FrameType_t GetCurrentFrameType(void) { return FRAME_TYPE_MULTIROTOR; }
#ifndef TEST_STARTUP
int32_t AlarmsSet(SystemAlarmsAlarmElem a, SystemAlarmsAlarmOptions s) { alarms[a] = s; return 0; }
int32_t AlarmsClear(SystemAlarmsAlarmElem a) { alarms[a] = SYSTEMALARMS_ALARM_OK; return 0; }
SystemAlarmsAlarmOptions AlarmsGet(SystemAlarmsAlarmElem a) { return alarms[a]; }
#else
static int alarm_mutex;
static unsigned alarm_lock_depth;
xSemaphoreHandle xSemaphoreCreateRecursiveMutex(void) { return &alarm_mutex; }
void xSemaphoreTakeRecursive(xSemaphoreHandle mutex, uint32_t timeout) {
    assert(mutex == &alarm_mutex && timeout == UINT32_MAX); ++alarm_lock_depth;
}
void xSemaphoreGiveRecursive(xSemaphoreHandle mutex) {
    assert(mutex == &alarm_mutex && alarm_lock_depth > 0); --alarm_lock_depth;
}
#endif
void xTaskCreate(void (*f)(void *), const char *name, unsigned size, void *p, unsigned priority, xTaskHandle *h) {}
void PIOS_TASK_MONITOR_RegisterTask(unsigned id, xTaskHandle h) {}
portTickType xTaskGetTickCount(void) { return ticks; }
static void next_iteration(void) {
    if (++iterations > iteration_limit) longjmp(stop_task, 1);
    ticks += 20;
#ifdef TEST_STARTUP
    /* Observe real task side effects BEFORE supplying the next queue result.
     * The script clock is deterministic; it is not an RTOS timing simulation. */
    if (iterations == 1) {
        assert(AlarmsGet(SYSTEMALARMS_ALARM_ACTUATOR) == SYSTEMALARMS_ALARM_CRITICAL);
        ActuatorCommandData actual; ActuatorCommandGet(&actual);
        for (int i = 0; i < 4; ++i) assert(actual.Channel[i] == 0 && hardware_output[i] == 0);
    }
    if (iterations == 61 && strcmp(scenario, "startup-absent") != 0)
        assert(AlarmsGet(SYSTEMALARMS_ALARM_ACTUATOR) == SYSTEMALARMS_ALARM_OK);
#endif
    if (iterations == 1 && strcmp(scenario, "failed-publication") == 0) {
        deny_publication = true; fail_thrust_read = 1;
    }
    if (iterations == 10 && powered_recovery) {
        assert(hardware_output[0] > 0);
        fail_thrust_read = 1;
    }
    if (iterations == 15 && powered_recovery) {
        assert(hardware_output[0] == 0);
        fail_thrust_read = 0;
    }
    if (iterations == 5) {
        if (strcmp(scenario, "late-failure") == 0) fail_thrust_read = 1;
        if (strcmp(scenario, "late-invalid") == 0) {
            uint8_t bad = 255; SystemSettingsThrustControlSet(&bad);
        }
        if (strcmp(scenario, "recovery") == 0) fail_thrust_read = 0;
    }
}
void vTaskDelayUntil(portTickType *t, portTickType period) { next_iteration(); *t = ticks; }
xQueueHandle xQueueCreate(unsigned n, unsigned size) { return (void *)1; }
int xQueueReceive(xQueueHandle q, void *ev, unsigned timeout) {
    next_iteration();
#ifdef TEST_STARTUP
    if (strcmp(scenario, "startup-absent") == 0 || iterations <= 5 ||
        (strcmp(scenario, "startup-relapse") == 0 && iterations >= 66)) return 0;
#endif
    return pdTRUE;
}
int32_t PIOS_RCVR_Read(uint32_t id, uint8_t channel) {
    if (channel == 1) return 1600;
    if (channel == 6) return 1700;
    return 1500;
}
void PIOS_Servo_Update(void) {}
void PIOS_Servo_Set(uint8_t channel, uint16_t value) {
    assert(channel < ACTUATORCOMMAND_CHANNEL_NUMELEM);
    hardware_output[channel] = shutdown_latched ? 0 : value;
    if (channel == 0 && iterations == 15) first_recovery_output = hardware_output[0];
}
void PIOS_LiteWing_BrushedPWM_Shutdown(void) {
    shutdown_latched = true;
    memset(hardware_output, 0, sizeof(hardware_output));
}
void PIOS_Servo_SetBankMode(uint8_t bank, int mode) {}
void PIOS_Servo_SetHz(const uint16_t *hz, const uint32_t *clock, uint8_t count) {}
uint8_t PIOS_Servo_GetPinBank(uint8_t pin) { return 0; }

int main(int argc, char **argv) {
    assert(argc == 2);
    scenario = argv[1];
    powered_recovery = strcmp(scenario, "powered-recovery") == 0 ||
        strcmp(scenario, "filtered-recovery") == 0 || strcmp(scenario, "feedforward-recovery") == 0;
    assert(sizeof(SystemSettingsThrustControlOptions) == 4);
    assert(offsetof(SystemSettingsData, ThrustControl) == 45);
    SystemSettingsInitialize(); ManualControlSettingsInitialize(); ManualControlCommandInitialize();
    FlightStatusInitialize(); AccessoryDesiredInitialize(); FlightTelemetryStatsInitialize();
    ReceiverActivityInitialize(); ActuatorSettingsInitialize(); MixerSettingsInitialize();
    ActuatorDesiredInitialize(); ActuatorCommandInitialize();
    uint8_t mode = (uint8_t)strtoul(argv[1], NULL, 10);
    SystemSettingsThrustControlSet(&mode);
    fail_thrust_read = strcmp(argv[1], "failed-read") == 0 || strcmp(scenario, "recovery") == 0;
    if (strcmp(scenario, "write-then-fail") == 0) fail_thrust_read = 2;
    bool invalid = mode > 1 || fail_thrust_read || strncmp(scenario, "late-", 5) == 0;
    if (strcmp(scenario, "recovery") == 0) invalid = false;
    if (strncmp(scenario, "late-", 5) == 0 || strcmp(scenario, "recovery") == 0) iteration_limit = 20;
    ManualControlSettingsData settings;
    ManualControlSettingsGet(&settings);
    for (unsigned i = 0; i < MANUALCONTROLSETTINGS_CHANNELGROUPS_NUMELEM; ++i) {
        ManualControlSettingsChannelGroupsToArray(settings.ChannelGroups)[i] = MANUALCONTROLSETTINGS_CHANNELGROUPS_GCS;
        ManualControlSettingsChannelNumberToArray(settings.ChannelNumber)[i] = i + 1;
        ManualControlSettingsChannelMinToArray(settings.ChannelMin)[i] = 1000;
        ManualControlSettingsChannelNeutralToArray(settings.ChannelNeutral)[i] = 1500;
        ManualControlSettingsChannelMaxToArray(settings.ChannelMax)[i] = 2000;
    }
    settings.FlightModeNumber = 1; settings.Deadband = 0;
    ManualControlSettingsSet(&settings);
    ManualControlCommandData command = { 0 };
    command.Connected = MANUALCONTROLCOMMAND_CONNECTED_TRUE;
    command.Thrust = .75f; command.Throttle = .8f; command.Collective = .6f;
    ManualControlCommandSet(&command);
#ifdef TEST_RECEIVER
    if (!setjmp(stop_task)) receiverTask(NULL);
    ManualControlCommandGet(&command);
    if (strcmp(scenario, "failed-publication") == 0) {
        assert(command.Thrust == .75f); /* Denied writes must not bypass access control. */
        assert(shutdown_latched);
        PIOS_Servo_Set(0, 800);
        assert(hardware_output[0] == 0);
        return 0;
    }
    float expected = invalid ? -1.0f : mode == 0 ? .2f : .4f;
    fprintf(stderr, "receiver mode=%s thrust=%f expected=%f connected=%u alarm=%u\n",
            argv[1], command.Thrust, expected, command.Connected, alarms[SYSTEMALARMS_ALARM_RECEIVER]);
    assert(fabsf(command.Thrust - expected) < .0001f);
    if (invalid) {
        assert(command.Connected == MANUALCONTROLCOMMAND_CONNECTED_FALSE);
        assert(command.Throttle == -1 && command.Collective == 0);
        assert(alarms[SYSTEMALARMS_ALARM_RECEIVER] == SYSTEMALARMS_ALARM_CRITICAL);
    }
#else
    /* Simulated ARMED state only: no actual drone APIs in this executable. */
    FlightStatusData fs = { .Armed = FLIGHTSTATUS_ARMED_ARMED }; FlightStatusSet(&fs);
    ActuatorDesiredData desired = { .Thrust = .4f }; ActuatorDesiredSet(&desired);
    ActuatorSettingsData as = { 0 };
    for (int i = 0; i < ACTUATORCOMMAND_CHANNEL_NUMELEM; ++i) {
        as.ChannelAddr[i] = i; as.ChannelMax[i] = 1000;
        as.ChannelType[i] = ACTUATORSETTINGS_CHANNELTYPE_PWM;
    }
    ActuatorSettingsSet(&as);
    MixerSettingsData ms = { 0 };
    ms.MaxAccel = 100; ms.AccelTime = ms.DecelTime = 1;
    if (strcmp(scenario, "filtered-recovery") == 0) ms.MaxAccel = .1f;
    if (strcmp(scenario, "feedforward-recovery") == 0) ms.FeedForward = .5f;
    for (int i = 0; i < MIXERSETTINGS_THROTTLECURVE1_NUMELEM; ++i) ms.ThrottleCurve1[i] = i * .25f;
    ms.Mixer1Type = ms.Mixer2Type = MIXERSETTINGS_MIXER1TYPE_MOTOR;
    ms.Mixer1Vector.ThrottleCurve1 = ms.Mixer2Vector.ThrottleCurve1 = 64;
    MixerSettingsSet(&ms);
#ifdef TEST_STARTUP
    assert(AlarmsInitialize() == 0);
    assert(AlarmsGet(SYSTEMALARMS_ALARM_BOOTFAULT) == SYSTEMALARMS_ALARM_UNINITIALISED);
    if (strcmp(scenario, "alarm-grace") == 0) {
        ticks = 2000;
        AlarmsSet(SYSTEMALARMS_ALARM_ACTUATOR, SYSTEMALARMS_ALARM_CRITICAL);
        ticks = 3000; AlarmsClear(SYSTEMALARMS_ALARM_ACTUATOR);
        assert(AlarmsGet(SYSTEMALARMS_ALARM_ACTUATOR) == SYSTEMALARMS_ALARM_CRITICAL);
        ticks = 3001; AlarmsClear(SYSTEMALARMS_ALARM_ACTUATOR);
        assert(AlarmsGet(SYSTEMALARMS_ALARM_ACTUATOR) == SYSTEMALARMS_ALARM_OK);
        /* A new failure escalates immediately, including during grace. */
        AlarmsSet(SYSTEMALARMS_ALARM_ACTUATOR, SYSTEMALARMS_ALARM_CRITICAL);
        assert(AlarmsGet(SYSTEMALARMS_ALARM_ACTUATOR) == SYSTEMALARMS_ALARM_CRITICAL);
        assert(alarm_lock_depth == 0);
        return 0;
    }
    fs.Armed = FLIGHTSTATUS_ARMED_DISARMED; FlightStatusSet(&fs);
    desired.Thrust = -1; ActuatorDesiredSet(&desired);
    command.Throttle = command.Thrust = -1; ManualControlCommandSet(&command);
#endif
    SettingsUpdatedCb(NULL); MixerSettingsUpdatedCb(NULL); ActuatorSettingsUpdatedCb(NULL);
    iteration_limit = 20; /* Allow existing throttle slew limiter to settle. */
#ifdef TEST_STARTUP
    iteration_limit = 70;
#endif
    if (!setjmp(stop_task)) actuatorTask(NULL);
#ifdef TEST_STARTUP
    ActuatorCommandData actual; ActuatorCommandGet(&actual);
    for (int i = 0; i < 4; ++i) assert(actual.Channel[i] == 0 && hardware_output[i] == 0);
    SystemAlarmsAlarmOptions want = strcmp(scenario, "startup-recovery") == 0 ?
        SYSTEMALARMS_ALARM_OK : SYSTEMALARMS_ALARM_CRITICAL;
    assert(AlarmsGet(SYSTEMALARMS_ALARM_ACTUATOR) == want);
    assert(AlarmsGet(SYSTEMALARMS_ALARM_BOOTFAULT) == SYSTEMALARMS_ALARM_UNINITIALISED);
    assert(alarm_lock_depth == 0);
    fprintf(stderr, "startup scenario=%s final_actuator_alarm=%u outputs_zero=1 boot_uninitialised=1\n", scenario, want);
    return 0;
#endif
    if (powered_recovery) {
        int limit = strcmp(scenario, "filtered-recovery") == 0 ? 2 :
            strcmp(scenario, "feedforward-recovery") == 0 ? 60 : 30;
        fprintf(stderr, "first recovery output=%u expected<=%d\n", first_recovery_output, limit);
        assert(first_recovery_output > 0 && first_recovery_output <= limit);
        return 0;
    }
    /* Half-scale mixer: thrust .4 -> 200; separate throttle .8 -> 400. */
    int expected = invalid ? 0 : mode == 0 ? 200 : 400;
    fprintf(stderr, "actuator mode=%s output=%u expected=%d alarm=%u\n", argv[1], hardware_output[0], expected, alarms[SYSTEMALARMS_ALARM_ACTUATOR]);
    assert(abs((int)hardware_output[0] - expected) <= 1);
    if (invalid) assert(alarms[SYSTEMALARMS_ALARM_ACTUATOR] == SYSTEMALARMS_ALARM_CRITICAL);
#endif
    return 0;
}
