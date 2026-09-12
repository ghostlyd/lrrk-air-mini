#include "litewing_attitude_trace_module.h"
#if CONFIG_LRRK_ATTITUDE_TRACE
#include "openpilot.h"
#include "litewingattitudetrace.h"
#include "litewing_attitude_trace.h"
#include "pios_litewing_brushed_pwm.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include <string.h>
#include <stddef.h>
_Static_assert(sizeof(LiteWingAttitudeTraceData) == 120, "trace wire size");
_Static_assert(offsetof(LiteWingAttitudeTraceData, Dt) == 16, "trace dt offset");
_Static_assert(offsetof(LiteWingAttitudeTraceData, Count) == 108, "trace count offset");
_Static_assert(offsetof(LiteWingAttitudeTraceData, Version) == 114, "trace version offset");
static struct lw_trace trace;
static portMUX_TYPE trace_lock = portMUX_INITIALIZER_UNLOCKED;
static bool attempted, ready;

int32_t LiteWingTraceInitialize(void)
{
    if (attempted) return -1;
    attempted = true;
    if (LiteWingAttitudeTraceInitialize() != 0 || !LiteWingAttitudeTraceHandle()) return -1;
    UAVObjMetadata metadata;
    if (LiteWingAttitudeTraceGetMetadata(&metadata) != 0 ||
        UAVObjGetGcsAccess(&metadata) != ACCESS_READONLY) return -1;
    ready = true;
    return 0;
}
int32_t LiteWingAttitudeTracePack(UAVObjHandle obj, uint16_t i, uint8_t *out)
{
    if (!obj || !out || i >= LW_TRACE_CAPACITY ||
        UAVObjGetID(obj) != LITEWINGATTITUDETRACE_OBJID || UAVObjGetNumBytes(obj) != 120) return -1;
    LiteWingAttitudeTraceData data = {0};
    data.Version = 2; data.RecordIndex = i; data.TriggerIndex = UINT16_MAX;
    struct lw_trace_record record;
    portENTER_CRITICAL(&trace_lock);
    data.State = !ready ? 0 : trace.frozen ? 3 : trace.triggered ? 2 : 1;
    data.Count = trace.count;
    if (trace.triggered) data.TriggerIndex = trace.trigger_index;
    bool valid = lw_trace_read(&trace, i, &record);
    portEXIT_CRITICAL(&trace_lock);
    if (valid) {
        data.TimeLow = (uint32_t)record.timestamp_us;
        data.TimeHigh = (uint32_t)(record.timestamp_us >> 32);
        data.Sequence = record.sequence; data.PwmCommits = record.commits;
        data.Dt = record.dt;
        memcpy(data.Accel, record.accel, sizeof data.Accel);
        memcpy(data.Gyro, record.gyro, sizeof data.Gyro);
        memcpy(data.Corrected, record.corrected, sizeof data.Corrected);
        memcpy(data.RPY, record.rpy, sizeof data.RPY);
        memcpy(data.PreBias, record.pre_bias, sizeof data.PreBias);
        memcpy(data.AppliedBias, record.applied_bias, sizeof data.AppliedBias);
        memcpy(data.Requested, record.requested, sizeof data.Requested);
        memcpy(data.Submitted, record.submitted, sizeof data.Submitted);
        data.PwmAvailable = record.pwm_available;
        data.KnownMask = record.known_mask; data.Suppression = record.suppression;
    }
    memcpy(out, &data, sizeof data);
    return 0;
}
void LiteWingAttitudeTraceRecord(float dt, const float a[3], const float g[3],
                                const float c[3], const float r[3],
                                const float pre[3], const float bias[3])
{
    if (!ready) return;
    struct lw_trace_record record = {.dt = dt};
    memcpy(record.pre_bias,pre,sizeof record.pre_bias);
    memcpy(record.applied_bias,bias,sizeof record.applied_bias);
    memcpy(record.accel,a,sizeof record.accel); memcpy(record.gyro,g,sizeof record.gyro);
    memcpy(record.corrected,c,sizeof record.corrected); memcpy(record.rpy,r,sizeof record.rpy);
    struct litewing_pwm_observation pwm;
    bool powered = false;
    /* No nested locks: snapshot acquisition is zero-wait and precedes trace lock. */
    if (PIOS_LiteWing_BrushedPWM_GetObservation(&pwm)) {
        record.pwm_available = 1; record.known_mask = pwm.known_mask & 15u;
        record.suppression = pwm.suppression; record.commits = pwm.commits;
        memcpy(record.requested,pwm.requested,sizeof record.requested);
        for (unsigned i=0; i<4; ++i) {
            if (record.known_mask & (1u<<i)) record.submitted[i] = pwm.submitted[i];
            powered |= record.submitted[i] != 0;
        }
        powered = powered && record.known_mask == 15 && !pwm.suppression &&
                  !pwm.write_errors && !pwm.stop_errors;
    }
    int64_t now = esp_timer_get_time();
    if (now < 0) return;
    record.timestamp_us = (uint64_t)now;
    portENTER_CRITICAL(&trace_lock);
    lw_trace_push(&trace, &record, powered);
    portEXIT_CRITICAL(&trace_lock);
}
#endif
