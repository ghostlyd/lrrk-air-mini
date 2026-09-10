/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Complete outer loop + generated UAVObjects + real PID/quaternion/delta-time
 * code. Controlled store/scheduler/cruise boundary; no hardware or motor I/O. */
#include <openpilot.h>
#include <stdio.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL: %s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#include MODULE_SOURCE

#if defined(SIMPOSIX) || defined(REVOLUTION) || !defined(PIOS_QUATERNION_STABILIZATION)
#error "fixture must exercise the selected non-simulator quaternion target"
#endif

struct object { uint32_t id, size; unsigned char data[2048]; UAVObjMetadata metadata; };
static struct object objects[8];
static unsigned object_count, registrations, publications, cruise_calls, dispatches;
static unsigned scheduler_creates, callback_connects;
static int fail_object;
static bool fail_scheduler, fail_callback;
static float cruise_thrust;
static AttitudeStateData expected_state;
static int callback_token;
static DelayedCallback callback;
static UAVObjEventCallback attitude_callback;
StabilizationData stabSettings;

UAVObjHandle UAVObjGetByID(uint32_t id) {
    for (unsigned i = 0; i < object_count; ++i) if (objects[i].id == id) return &objects[i];
    return NULL;
}
UAVObjHandle UAVObjRegister(uint32_t id, bool single, bool settings, bool priority,
                           uint32_t size, UAVObjInitializeCallback cb) {
    if (++registrations == (unsigned)fail_object) return NULL;
    CHECK(object_count < 8 && size <= 2048 && !UAVObjGetByID(id));
    struct object *o = &objects[object_count++]; o->id = id; o->size = size;
    cb(o, 0); return o;
}
int32_t UAVObjGetData(UAVObjHandle h, void *out) {
    CHECK(h); struct object *o = h; memcpy(out, o->data, o->size); return 0;
}
int32_t UAVObjSetData(UAVObjHandle h, const void *in) {
    CHECK(h); struct object *o = h; memcpy(o->data, in, o->size);
    if (o->id == RATEDESIRED_OBJID) ++publications;
    return 0;
}
int32_t UAVObjGetInstanceData(UAVObjHandle h, uint16_t instance, void *out) {
    CHECK(instance == 0); return UAVObjGetData(h, out);
}
int32_t UAVObjSetInstanceData(UAVObjHandle h, uint16_t instance, const void *in) {
    CHECK(instance == 0); return UAVObjSetData(h, in);
}
int32_t UAVObjGetDataField(UAVObjHandle h, void *out, uint32_t offset, uint32_t size) {
    CHECK(h); struct object *o = h; CHECK(offset + size <= o->size);
    memcpy(out, o->data + offset, size); return 0;
}
int32_t UAVObjSetDataField(UAVObjHandle h, const void *in, uint32_t offset, uint32_t size) {
    CHECK(h); struct object *o = h; CHECK(offset + size <= o->size);
    memcpy(o->data + offset, in, size); return 0;
}
int32_t UAVObjSetMetadata(UAVObjHandle h, const UAVObjMetadata *m) { CHECK(h); ((struct object *)h)->metadata = *m; return 0; }
int32_t UAVObjConnectCallback(UAVObjHandle h, UAVObjEventCallback cb, uint8_t mask) {
    ++callback_connects;
    CHECK(h == AttitudeStateHandle() && cb && mask == EV_MASK_ALL_UPDATES && !attitude_callback);
    if (fail_callback) return -1;
    attitude_callback = cb; return 0;
}
DelayedCallbackInfo *PIOS_CALLBACKSCHEDULER_Create(DelayedCallback cb, DelayedCallbackPriority priority,
    DelayedCallbackPriorityTask task, int16_t id, uint32_t stack) {
    ++scheduler_creates;
    CHECK(!callback && cb && priority == CALLBACK_PRIORITY_REGULAR);
    CHECK(task == CALLBACK_TASK_STABILIZATIONOUTERLOOP && id == CALLBACKINFO_RUNNING_STABILIZATION0);
    CHECK(stack == PIOS_STABILIZATION_STACK_SIZE);
    if (fail_scheduler) return NULL;
    callback = cb; return (DelayedCallbackInfo *)&callback_token;
}
int32_t PIOS_CALLBACKSCHEDULER_Dispatch(DelayedCallbackInfo *handle) {
    CHECK(handle == (DelayedCallbackInfo *)&callback_token && callback);
    ++dispatches; callback(); return -1;
}
uint32_t PIOS_DELAY_GetRaw(void) { return 0; }
uint32_t PIOS_DELAY_DiffuS(uint32_t before) { return 2000; }
void cruisecontrol_compute_factor(AttitudeStateData *state, float thrust) {
    CHECK(state && memcmp(state, &expected_state, sizeof(*state)) == 0);
    ++cruise_calls; cruise_thrust = thrust;
}

int main(int argc, char **argv) {
    CHECK(argc == 2);
    if (!strcmp(argv[1], "stack-bytes")) { printf("%u\n", (unsigned)STACK_SIZE_BYTES); return 0; }
#ifndef TEST_ORIGINAL
    if (!strncmp(argv[1], "startup-object-", 15)) fail_object = atoi(argv[1] + 15);
    fail_scheduler = !strcmp(argv[1], "startup-scheduler");
    fail_callback = !strcmp(argv[1], "startup-callback");
    if (!strcmp(argv[1], "startup-existing")) {
        CHECK(RateDesiredInitialize() == 0 && StabilizationDesiredInitialize() == 0);
        CHECK(AttitudeStateInitialize() == 0 && StabilizationStatusInitialize() == 0);
        CHECK(FlightStatusInitialize() == 0 && ManualControlCommandInitialize() == 0);
    }
    if (!strncmp(argv[1], "startup-", 8)) {
        bool should_fail = fail_object || fail_scheduler || fail_callback;
        unsigned before = registrations;
        int32_t result = PIOS_LiteWing_StabilizationOuterloopInitialize();
        CHECK((result != 0) == should_fail);
        CHECK(registrations == before + (fail_object ? (unsigned)fail_object :
              !strcmp(argv[1], "startup-existing") ? 0U : 6U));
        CHECK(scheduler_creates == (unsigned)(!fail_object));
        CHECK(callback_connects == (unsigned)(!fail_object && !fail_scheduler));
        CHECK((attitude_callback != NULL) == (!should_fail));
        unsigned side_effects = registrations + scheduler_creates + callback_connects;
        CHECK(PIOS_LiteWing_StabilizationOuterloopInitialize() != 0);
        CHECK(registrations + scheduler_creates + callback_connects == side_effects);
        return 0;
    }
    CHECK(PIOS_LiteWing_StabilizationOuterloopInitialize() == 0);
#else
    stabilizationOuterloopInit();
#endif
    CHECK(object_count == 6 && callback && attitude_callback);
    AttitudeStateData state = { .q1 = 1.0f };
    StabilizationDesiredData desired = { .Roll = .25f, .Pitch = -.5f, .Yaw = .75f, .Thrust = .375f };
    RateDesiredData stale = { .Roll = 101, .Pitch = 102, .Yaw = 103, .Thrust = .9375f };
    StabilizationStatusData modes = { 0 };
    for (unsigned i = 0; i < AXES; ++i) StabilizationStatusOuterLoopToArray(modes.OuterLoop)[i] = STABILIZATIONSTATUS_OUTERLOOP_DIRECT;
    float want_roll = .25f, want_pitch = -.5f, want_yaw = .75f;
    if (!strncmp(argv[1], "attitude-", 9)) {
        unsigned axis = !strcmp(argv[1], "attitude-roll") ? 0 : !strcmp(argv[1], "attitude-pitch") ? 1 : 2;
        CHECK(axis != 2 || !strcmp(argv[1], "attitude-yaw"));
        StabilizationStatusOuterLoopToArray(modes.OuterLoop)[axis] = STABILIZATIONSTATUS_OUTERLOOP_ATTITUDE;
        desired.Roll = axis == 0 ? 10 : 0;
        desired.Pitch = axis == 1 ? -10 : 0;
        desired.Yaw = axis == 2 ? 10 : 0;
        state.Roll = axis == 0 ? 5 : 0;
        state.Pitch = axis == 1 ? -5 : 0;
        state.Yaw = axis == 2 ? 5 : 0;
        stabSettings.outerPids[axis].p = 2;
        want_roll = axis == 0 ? 10 : 0;
        want_pitch = axis == 1 ? -10 : 0;
        want_yaw = axis == 2 ? 10 : 0;
    } else if (!strncmp(argv[1], "mixed-current-", 14)) {
        unsigned direct = !strcmp(argv[1], "mixed-current-roll") ? 0 :
                          !strcmp(argv[1], "mixed-current-pitch") ? 1 : 2;
        CHECK(direct != 2 || !strcmp(argv[1], "mixed-current-yaw"));
        const float current_rpy[3] = { 13, -17, 23 };
        const float desired_rpy[3] = { 25, -29, 37 };
        state.Roll = current_rpy[0]; state.Pitch = current_rpy[1]; state.Yaw = current_rpy[2];
        desired.Roll = desired_rpy[0]; desired.Pitch = desired_rpy[1]; desired.Yaw = desired_rpy[2];
        for (unsigned axis = 0; axis < 3; ++axis) {
            StabilizationStatusOuterLoopToArray(modes.OuterLoop)[axis] =
                axis == direct ? STABILIZATIONSTATUS_OUTERLOOP_DIRECT : STABILIZATIONSTATUS_OUTERLOOP_ATTITUDE;
            stabSettings.outerPids[axis].p = 2;
        }
        float effective_rpy[3], desired_q[4], current_q[4], error_q[4], error_rpy[3];
        for (unsigned axis = 0; axis < 3; ++axis)
            effective_rpy[axis] = axis == direct ? current_rpy[axis] : desired_rpy[axis];
        RPY2Quaternion(current_rpy, current_q);
        RPY2Quaternion(effective_rpy, desired_q);
        quat_inverse(desired_q);
        quat_mult(desired_q, current_q, error_q);
        quat_inverse(error_q);
        Quaternion2RPY(error_q, error_rpy);
        want_roll = direct == 0 ? desired_rpy[0] : 2 * error_rpy[0];
        want_pitch = direct == 1 ? desired_rpy[1] : 2 * error_rpy[1];
        want_yaw = direct == 2 ? desired_rpy[2] : 2 * error_rpy[2];
    } else CHECK(!strcmp(argv[1], "direct"));
    float state_rpy[3] = {state.Roll, state.Pitch, state.Yaw}, state_q[4];
    RPY2Quaternion(state_rpy, state_q);
    state.q1 = state_q[0]; state.q2 = state_q[1]; state.q3 = state_q[2]; state.q4 = state_q[3];
    expected_state = state; CHECK(AttitudeStateSet(&state) == 0);
    CHECK(StabilizationStatusSet(&modes) == 0);
    /* Multiple values include zero and the negative disarmed-input sentinel;
     * stale RateDesired.Thrust must never substitute for the new direct input. */
    const float thrust[] = { .375f, 0, -1, 1 };
    for (unsigned i = 0; i < 4; ++i) {
        desired.Thrust = thrust[i]; CHECK(StabilizationDesiredSet(&desired) == 0);
        CHECK(RateDesiredSet(&stale) == 0); unsigned before = publications;
        UAVObjEvent event = { .obj = AttitudeStateHandle(), .event = EV_UPDATED };
        unsigned calls = dispatches;
        /* Existing callback runs every fourth attitude update, beginning with
         * the first. Keep this full consumer path, not a copied task body. */
        for (unsigned update = 0; update < OUTERLOOP_SKIPCOUNT; ++update) attitude_callback(&event);
        CHECK(dispatches == calls + 1 && publications == before + 1 && cruise_calls == i + 1);
        RateDesiredData actual; CHECK(RateDesiredGet(&actual) == 0);
        CHECK(fabsf(actual.Roll - want_roll) < 1e-4f);
        CHECK(fabsf(actual.Pitch - want_pitch) < 1e-4f && fabsf(actual.Yaw - want_yaw) < 1e-4f);
        CHECK(actual.Thrust == thrust[i] && cruise_thrust == thrust[i]);
    }
    return 0;
}
