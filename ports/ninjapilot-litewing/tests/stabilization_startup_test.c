/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Whole generated Stabilization module + real module table/UAVObjects. */
#include <openpilot.h>
#include <stdio.h>
#include <pios_litewing_modules.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL: %s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#include MODULE_SOURCE

struct object { uint32_t id, size; unsigned char data[4096]; UAVObjMetadata metadata; };
static struct object objects[20];
static unsigned object_count, registrations, callback_calls, subscription_count;
static unsigned watchdog_calls, outer_calls, inner_calls, later_inits, later_starts;
static int fail_object, fail_callback;
static bool fail_watchdog, fail_sin, fail_outer, fail_inner;
static uint32_t fail_get_id, fail_set_id;
struct subscription { UAVObjHandle object; UAVObjEventCallback callback; uint8_t mask; };
static struct subscription subscriptions[8];

UAVObjHandle UAVObjGetByID(uint32_t id)
{
    for (unsigned i = 0; i < object_count; ++i) if (objects[i].id == id) return &objects[i];
    return NULL;
}

UAVObjHandle UAVObjRegister(uint32_t id, bool single, bool settings, bool priority,
                           uint32_t size, UAVObjInitializeCallback callback)
{
    if (++registrations == (unsigned)fail_object) return NULL;
    CHECK(object_count < 20 && size <= sizeof(objects[0].data) && !UAVObjGetByID(id));
    struct object *object = &objects[object_count++];
    object->id = id; object->size = size; callback(object, 0); return object;
}

int32_t UAVObjGetData(UAVObjHandle handle, void *out)
{
    if (!handle || ((struct object *)handle)->id == fail_get_id) return -1;
    struct object *object = handle; memcpy(out, object->data, object->size); return 0;
}
int32_t UAVObjSetData(UAVObjHandle handle, const void *in)
{
    if (!handle || ((struct object *)handle)->id == fail_set_id) return -1;
    struct object *object = handle; memcpy(object->data, in, object->size); return 0;
}
int32_t UAVObjGetInstanceData(UAVObjHandle handle, uint16_t instance, void *out)
{ CHECK(instance == 0); return UAVObjGetData(handle, out); }
int32_t UAVObjSetInstanceData(UAVObjHandle handle, uint16_t instance, const void *in)
{ CHECK(instance == 0); return UAVObjSetData(handle, in); }
int32_t UAVObjGetDataField(UAVObjHandle handle, void *out, uint32_t offset, uint32_t size)
{
    if (!handle || ((struct object *)handle)->id == fail_get_id) return -1;
    struct object *object = handle; CHECK(offset + size <= object->size);
    memcpy(out, object->data + offset, size); return 0;
}
int32_t UAVObjSetDataField(UAVObjHandle handle, const void *in, uint32_t offset, uint32_t size)
{
    if (!handle || ((struct object *)handle)->id == fail_set_id) return -1;
    struct object *object = handle; CHECK(offset + size <= object->size);
    memcpy(object->data + offset, in, size); return 0;
}
int32_t UAVObjSetMetadata(UAVObjHandle handle, const UAVObjMetadata *metadata)
{ CHECK(handle); ((struct object *)handle)->metadata = *metadata; return 0; }

int32_t UAVObjConnectCallback(UAVObjHandle object, UAVObjEventCallback callback, uint8_t mask)
{
    ++callback_calls; CHECK(object && callback && mask == EV_MASK_ALL_UPDATES);
    if (callback_calls == (unsigned)fail_callback) return -1;
    CHECK(subscription_count < 8);
    subscriptions[subscription_count++] = (struct subscription){ object, callback, mask };
    return 0;
}

static void check_subscription_prefix(unsigned count)
{
    const struct subscription expected[] = {
        { StabilizationSettingsHandle(), SettingsUpdatedCb, EV_MASK_ALL_UPDATES },
        { ManualControlCommandHandle(), FlightModeSwitchUpdatedCb, EV_MASK_ALL_UPDATES },
        { StabilizationBankHandle(), BankUpdatedCb, EV_MASK_ALL_UPDATES },
        { StabilizationSettingsBank1Handle(), SettingsBankUpdatedCb, EV_MASK_ALL_UPDATES },
        { StabilizationSettingsBank2Handle(), SettingsBankUpdatedCb, EV_MASK_ALL_UPDATES },
        { StabilizationSettingsBank3Handle(), SettingsBankUpdatedCb, EV_MASK_ALL_UPDATES },
        { StabilizationDesiredHandle(), StabilizationDesiredUpdatedCb, EV_MASK_ALL_UPDATES },
        { FlightStatusHandle(), ArmedStatusUpdatedCb, EV_MASK_ALL_UPDATES },
    };
    CHECK(subscription_count == count);
    for (unsigned i = 0; i < count; ++i) {
        CHECK(subscriptions[i].object == expected[i].object);
        CHECK(subscriptions[i].callback == expected[i].callback);
        CHECK(subscriptions[i].mask == expected[i].mask);
    }
}

bool PIOS_WDG_RegisterFlag(uint16_t flag)
{ ++watchdog_calls; CHECK(flag == PIOS_WDG_STABILIZATION); return !fail_watchdog; }
int sin_lookup_initalize(void) { return fail_sin ? -1 : 0; }
int32_t PIOS_LiteWing_StabilizationOuterloopInitialize(void)
{ ++outer_calls; return fail_outer ? -1 : 0; }
int32_t PIOS_LiteWing_StabilizationInnerloopInitialize(void)
{ ++inner_calls; return fail_inner ? -1 : 0; }
void stabilizationOuterloopInit(void) { (void)PIOS_LiteWing_StabilizationOuterloopInitialize(); }
void stabilizationInnerloopInit(void) { (void)PIOS_LiteWing_StabilizationInnerloopInitialize(); }
void stabilizationInnerloopResetAxisLock(void) {}

int32_t AttitudeInitialize(void) { return 0; }
int32_t AttitudeStart(void) { return 0; }
#define LATER(Name) int32_t Name##Initialize(void) { ++later_inits; return 0; } \
    int32_t Name##Start(void) { ++later_starts; return 0; }
LATER(Actuator) LATER(Receiver) LATER(ManualControl) LATER(Telemetry)
int32_t LiteWingBatteryInitialize(void) { return 0; }
int32_t LiteWingBatteryStart(void) { return 0; }

static void initialize_existing_objects(void)
{
    CHECK(StabilizationDesiredInitialize() == 0 && StabilizationSettingsInitialize() == 0);
    CHECK(StabilizationStatusInitialize() == 0 && StabilizationBankInitialize() == 0);
    CHECK(StabilizationSettingsBank1Initialize() == 0 && StabilizationSettingsBank2Initialize() == 0);
    CHECK(StabilizationSettingsBank3Initialize() == 0 && RateDesiredInitialize() == 0);
    CHECK(ManualControlCommandInitialize() == 0 && RelayTuningSettingsInitialize() == 0);
    CHECK(RelayTuningInitialize() == 0);
}

int main(int argc, char **argv)
{
    CHECK(argc == 2); const char *scenario = argv[1];
    CHECK(FlightStatusInitialize() == 0); registrations = 0;
    if (!strncmp(scenario, "object-", 7)) fail_object = atoi(scenario + 7);
    fail_sin = !strcmp(scenario, "sin");
    fail_outer = !strcmp(scenario, "outer"); fail_inner = !strcmp(scenario, "inner");
    if (!strcmp(scenario, "existing")) { initialize_existing_objects(); registrations = 0; }
    if (!strcmp(scenario, "premature")) {
        CHECK(StabilizationStart() != 0 && callback_calls == 0 && watchdog_calls == 0);
    }
    bool init_failure = fail_object || fail_sin || fail_outer || fail_inner;
    int32_t result = PIOS_LiteWing_ModulesInitialize();
    if (init_failure) {
        CHECK(result != 0 && later_inits == 0 && later_starts == 0);
        CHECK(outer_calls == (unsigned)(!fail_object && !fail_sin));
        CHECK(inner_calls == (unsigned)(!fail_object && !fail_sin && !fail_outer));
        CHECK(PIOS_LiteWing_ModulesStart() != 0 && callback_calls == 0 && watchdog_calls == 0);
        unsigned effects = registrations + outer_calls + inner_calls;
        CHECK(StabilizationInitialize() != 0);
        CHECK(registrations + outer_calls + inner_calls == effects);
        return 0;
    }
    CHECK(result == 0 && later_inits == 4 && outer_calls == 1 && inner_calls == 1);
    CHECK(registrations == (!strcmp(scenario, "existing") ? 0U : 11U));
    unsigned init_effects = registrations + outer_calls + inner_calls;
    CHECK(StabilizationInitialize() != 0);
    CHECK(registrations + outer_calls + inner_calls == init_effects);
    if (!strncmp(scenario, "callback-", 9)) fail_callback = atoi(scenario + 9);
    fail_watchdog = !strcmp(scenario, "watchdog");
    if (!strcmp(scenario, "read-settings")) fail_get_id = STABILIZATIONSETTINGS_OBJID;
    if (!strcmp(scenario, "read-desired")) fail_get_id = STABILIZATIONDESIRED_OBJID;
    if (!strcmp(scenario, "write-status")) fail_set_id = STABILIZATIONSTATUS_OBJID;
    if (!strcmp(scenario, "read-manual")) fail_get_id = MANUALCONTROLCOMMAND_OBJID;
    if (!strcmp(scenario, "read-bank-settings")) fail_get_id = STABILIZATIONSETTINGSBANK1_OBJID;
    if (!strcmp(scenario, "write-bank")) fail_set_id = STABILIZATIONBANK_OBJID;
    if (!strcmp(scenario, "read-bank")) fail_get_id = STABILIZATIONBANK_OBJID;
    bool start_failure = fail_callback || fail_watchdog || fail_get_id || fail_set_id;
    result = PIOS_LiteWing_ModulesStart();
    if (start_failure) {
        CHECK(result != 0 && later_starts == 0);
        CHECK(callback_calls == (unsigned)(fail_watchdog ? 0 : fail_callback ? fail_callback : 8));
        check_subscription_prefix(fail_watchdog ? 0 : fail_callback ? fail_callback - 1 : 8);
    } else {
        CHECK(result == 0 && later_starts == 4 && callback_calls == 8 && watchdog_calls == 1);
        check_subscription_prefix(8);
        StabilizationStatusData status; CHECK(StabilizationStatusGet(&status) == 0);
        StabilizationBankData bank; CHECK(StabilizationBankGet(&bank) == 0);
    }
    unsigned effects = callback_calls + watchdog_calls;
    CHECK(StabilizationStart() != 0 && callback_calls + watchdog_calls == effects);
    return 0;
}
