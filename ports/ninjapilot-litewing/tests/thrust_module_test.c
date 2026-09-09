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
    assert(h); struct object *obj = h; memcpy(obj->data, in, obj->size); return 0;
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
int8_t UAVObjReadOnly(UAVObjHandle h) { return 0; }
int32_t UAVObjConnectCallback(UAVObjHandle h, UAVObjEventCallback cb, uint8_t mask) { return 0; }
int32_t UAVObjConnectQueue(UAVObjHandle h, xQueueHandle q, uint8_t mask) { return 0; }
FrameType_t GetCurrentFrameType(void) { return FRAME_TYPE_MULTIROTOR; }
int32_t AlarmsSet(SystemAlarmsAlarmElem a, SystemAlarmsAlarmOptions s) { alarms[a] = s; return 0; }
int32_t AlarmsClear(SystemAlarmsAlarmElem a) { alarms[a] = SYSTEMALARMS_ALARM_OK; return 0; }
SystemAlarmsAlarmOptions AlarmsGet(SystemAlarmsAlarmElem a) { return alarms[a]; }
void xTaskCreate(void (*f)(void *), const char *name, unsigned size, void *p, unsigned priority, xTaskHandle *h) {}
void PIOS_TASK_MONITOR_RegisterTask(unsigned id, xTaskHandle h) {}
portTickType xTaskGetTickCount(void) { return ticks; }
static void next_iteration(void) {
    if (++iterations > iteration_limit) longjmp(stop_task, 1);
    ticks += 20;
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
int xQueueReceive(xQueueHandle q, void *ev, unsigned timeout) { next_iteration(); return pdTRUE; }
int32_t PIOS_RCVR_Read(uint32_t id, uint8_t channel) {
    if (channel == 1) return 1600;
    if (channel == 6) return 1700;
    return 1500;
}
void PIOS_Servo_Update(void) {}
void PIOS_Servo_Set(uint8_t channel, uint16_t value) { assert(channel < ACTUATORCOMMAND_CHANNEL_NUMELEM); hardware_output[channel] = value; }
void PIOS_Servo_SetBankMode(uint8_t bank, int mode) {}
void PIOS_Servo_SetHz(const uint16_t *hz, const uint32_t *clock, uint8_t count) {}
uint8_t PIOS_Servo_GetPinBank(uint8_t pin) { return 0; }

int main(int argc, char **argv) {
    assert(argc == 2);
    scenario = argv[1];
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
    for (int i = 0; i < MIXERSETTINGS_THROTTLECURVE1_NUMELEM; ++i) ms.ThrottleCurve1[i] = i * .25f;
    ms.Mixer1Type = ms.Mixer2Type = MIXERSETTINGS_MIXER1TYPE_MOTOR;
    ms.Mixer1Vector.ThrottleCurve1 = ms.Mixer2Vector.ThrottleCurve1 = 64;
    MixerSettingsSet(&ms);
    SettingsUpdatedCb(NULL); MixerSettingsUpdatedCb(NULL); ActuatorSettingsUpdatedCb(NULL);
    iteration_limit = 20; /* Allow existing throttle slew limiter to settle. */
    if (!setjmp(stop_task)) actuatorTask(NULL);
    /* Half-scale mixer: thrust .4 -> 200; separate throttle .8 -> 400. */
    int expected = invalid ? 0 : mode == 0 ? 200 : 400;
    fprintf(stderr, "actuator mode=%s output=%u expected=%d alarm=%u\n", argv[1], hardware_output[0], expected, alarms[SYSTEMALARMS_ALARM_ACTUATOR]);
    assert(abs((int)hardware_output[0] - expected) <= 1);
    if (invalid) assert(alarms[SYSTEMALARMS_ALARM_ACTUATOR] == SYSTEMALARMS_ALARM_CRITICAL);
#endif
    return 0;
}
