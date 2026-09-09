/* Reuse the existing board's controlled services/storage, but replace its
 * EventDispatcher/Alarms doubles with the complete production libraries.
 * Rename only test doubles here; no firmware source body is changed. */
#include "openpilot.h"
#include <callbackinfo.h>
#define EventDispatcherInitialize unused_board_EventDispatcherInitialize
#define AlarmsInitialize unused_board_AlarmsInitialize
#define AlarmsSet unused_board_AlarmsSet
#define SystemAlarmsHandle unused_board_SystemAlarmsHandle
#define pios_malloc board_malloc
#define pios_free board_free
#define main unused_board_main
#include "board_startup_test.c"
#undef EventDispatcherInitialize
#undef AlarmsInitialize
#undef AlarmsSet
#undef SystemAlarmsHandle
#undef pios_malloc
#undef pios_free
#undef main

static struct mutex_state { bool live; unsigned held; } locks[2];
static unsigned mutex_creates, callback_creates, callback_dispatches, alarm_initializers;
static bool direct_alarm, periodic_allocation, queue_live, queue_pending, callback_pending;
static bool scheduler_signal_full;
static unsigned queue_item_size, callbacks_seen;
static unsigned char queue_storage[256];
static int queue_token, callback_token;
static DelayedCallback scheduled_callback;
static uint32_t now;

static bool inject(const char *name)
{
    if (strcmp(scenario, name) != 0) return false;
    failed = true;
    return true;
}

xSemaphoreHandle xSemaphoreCreateRecursiveMutex(void)
{
    unsigned index = direct_alarm ? 1 : mutex_creates;
    CHECK(index < 2);
    mutex_creates++;
    if (inject(index == 0 ? "event-mutex" : "alarm-mutex")) return NULL;
    CHECK(!locks[index].live);
    locks[index].live = true;
    return &locks[index];
}
int xSemaphoreTakeRecursive(xSemaphoreHandle handle, uint32_t ticks)
{
    CHECK(handle == &locks[0] || handle == &locks[1]);
    struct mutex_state *lock = handle;
    CHECK(lock->live && ticks == portMAX_DELAY);
    lock->held++;
    return pdTRUE;
}
int xSemaphoreGiveRecursive(xSemaphoreHandle handle)
{
    CHECK(handle == &locks[0] || handle == &locks[1]);
    struct mutex_state *lock = handle;
    CHECK(lock->live && lock->held > 0);
    lock->held--;
    return pdTRUE;
}
void vSemaphoreDelete(xSemaphoreHandle handle)
{
    CHECK(handle == &locks[0]);
    CHECK(locks[0].live && locks[0].held == 0);
    locks[0].live = false;
}
xQueueHandle xQueueCreate(unsigned count, unsigned size)
{
    CHECK(count == 20 && size > sizeof(UAVObjEvent) && size <= sizeof(queue_storage));
    CHECK(locks[0].live && !queue_live);
    if (inject("event-queue")) return NULL;
    queue_live = true;
    queue_item_size = size;
    return &queue_token;
}
void vQueueDelete(xQueueHandle handle)
{
    CHECK(handle == &queue_token && queue_live && !callback_pending);
    queue_live = false;
}
int xQueueSend(xQueueHandle handle, const void *item, unsigned ticks)
{
    CHECK(handle == &queue_token && queue_live && ticks == 0);
    if (queue_pending) return 0;
    memcpy(queue_storage, item, queue_item_size);
    queue_pending = true;
    return pdTRUE;
}
int xQueueReceive(xQueueHandle handle, void *out, unsigned ticks)
{
    CHECK(handle == &queue_token && queue_live && ticks == 0);
    if (!queue_pending) return 0;
    memcpy(out, queue_storage, queue_item_size);
    queue_pending = false;
    return pdTRUE;
}
uint32_t xTaskGetTickCount(void) { return now; }
DelayedCallbackInfo *PIOS_CALLBACKSCHEDULER_Create(DelayedCallback cb,
    DelayedCallbackPriority priority, DelayedCallbackPriorityTask task_priority,
    int16_t callback_id, uint32_t stack)
{
    CHECK(queue_live && locks[0].live);
    CHECK(priority == CALLBACK_PRIORITY_CRITICAL && task_priority == CALLBACK_TASK_FLIGHTCONTROL);
    CHECK(callback_id == CALLBACKINFO_RUNNING_EVENTDISPATCHER && stack == 4096 * 4);
    callback_creates++;
    if (inject("event-callback")) return NULL;
    scheduled_callback = cb;
    /* Pinned vSemaphoreCreateBinary creates an initially full signal even
     * though this callback has not yet been marked pending. */
    scheduler_signal_full = true;
    return (DelayedCallbackInfo *)&callback_token;
}
int32_t PIOS_CALLBACKSCHEDULER_Dispatch(DelayedCallbackInfo *cb)
{
    CHECK(cb == (DelayedCallbackInfo *)&callback_token && scheduled_callback);
    callback_dispatches++;
    bool signal_was_full = scheduler_signal_full;
    callback_pending = true;
    scheduler_signal_full = true;
    /* Real signal may already be full: zero does not mean a lost callback. */
    return signal_was_full ? 0 : pdTRUE;
}
int32_t PIOS_CALLBACKSCHEDULER_Schedule(DelayedCallbackInfo *cb, int32_t ms, DelayedCallbackUpdateMode mode)
{
    CHECK(cb == (DelayedCallbackInfo *)&callback_token && ms >= 0);
    CHECK(mode == CALLBACK_UPDATEMODE_SOONER);
    return 1;
}

UAVObjHandle SystemAlarmsHandle(void) { return objects_ready ? &objects[4] : NULL; }
int32_t SystemAlarmsInitialize(void)
{
    alarm_initializers++;
    if (inject("alarm-object")) return -1;
    if (objects_ready) return -2;
    /* Model registration's default initialization, not preserved nonexistent data. */
    memset(&alarm_data, 0, sizeof(alarm_data));
    objects_ready = true;
    return 0;
}
void SystemAlarmsAlarmGet(SystemAlarmsAlarmData *out)
{ CHECK(objects_ready); memcpy(out, &alarm_data.Alarm, sizeof(*out)); }
void SystemAlarmsAlarmSet(SystemAlarmsAlarmData *in)
{
    CHECK(objects_ready && locks[1].live && locks[1].held > 0);
    memcpy(&alarm_data.Alarm, in, sizeof(*in));
}

void *pios_malloc(size_t size)
{
    if (!periodic_allocation) return board_malloc(size);
    CHECK(locks[0].held > 0);
    if (inject("periodic-allocation")) return NULL;
    return malloc(size);
}
void pios_free(void *pointer) { board_free(pointer); }

static void observed_event(UAVObjEvent *event)
{
    CHECK(event->obj == &objects[3] && event->instId == 0 && event->event == EV_UPDATED);
    callbacks_seen++;
}

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    scenario = argv[1];
    direct_alarm = strncmp(scenario, "alarm-direct", 12) == 0 || strcmp(scenario, "alarm-object") == 0;
    if (direct_alarm) {
        if (strcmp(scenario, "alarm-object") == 0) {
            CHECK(AlarmsInitialize() == -1);
            CHECK(alarm_initializers == 1 && mutex_creates == 0 && !objects_ready);
            return 0;
        }
        objects_ready = strcmp(scenario, "alarm-direct-existing") == 0;
        alarm_data.Alarm.BootFault = SYSTEMALARMS_ALARM_CRITICAL;
        CHECK(AlarmsInitialize() == 0);
        CHECK(alarm_initializers == (strcmp(scenario, "alarm-direct-existing") == 0 ? 0u : 1u));
        CHECK(alarm_data.Alarm.BootFault == (strcmp(scenario, "alarm-direct-existing") == 0
            ? SYSTEMALARMS_ALARM_CRITICAL : SYSTEMALARMS_ALARM_UNINITIALISED));
        CHECK(locks[1].live && locks[1].held == 0);
        return 0;
    }

    /* These real initializer failures must propagate through the real board
     * and entry point into zero module starts, not merely a local -1 return. */
    app_main();
    CHECK(locks[0].held == 0 && locks[1].held == 0);
    if (strncmp(scenario, "event-", 6) == 0 || strcmp(scenario, "alarm-mutex") == 0) {
        CHECK(failed && !PIOS_LiteWing_BoardServicesInitialized());
        CHECK(modules == 0 && system_inits == 0 && shutdown_requests == 1);
        CHECK(later_calls == 0 && !hardware_started);
        if (strncmp(scenario, "event-", 6) == 0) {
            CHECK(!objects_ready && !queue_live && !locks[0].live);
            CHECK(callback_dispatches == 0 && !callback_pending);
            CHECK(callback_creates == (strcmp(scenario, "event-callback") == 0 ? 1u : 0u));
        } else {
            CHECK(objects_ready && !locks[1].live && alarm_initializers == 0);
            CHECK(allocations == 0); /* Telemetry was never initialized. */
        }
        return 0;
    }
    CHECK(PIOS_LiteWing_BoardServicesInitialized() && modules == 1 && system_inits == 1);
    CHECK(shutdown_requests == 0);
    CHECK(alarm_data.Alarm.BootFault == SYSTEMALARMS_ALARM_UNINITIALISED);
    CHECK(callback_dispatches == 1 && callback_pending && scheduler_signal_full);
    UAVObjEvent event = { .obj = &objects[3], .instId = 0, .event = EV_UPDATED };
    if (strcmp(scenario, "periodic-allocation") == 0) {
        periodic_allocation = true;
        CHECK(EventPeriodicCallbackCreate(&event, observed_event, 10) == -1);
        CHECK(locks[0].held == 0); /* Allocation error must release the mutex. */
        return 0;
    }
    /* Queue dispatch remains usable, including a signal already pending. */
    CHECK(EventCallbackDispatch(&event, observed_event) == pdTRUE);
    CHECK(callback_dispatches == 2 && callback_pending);
    /* Simulate scheduler consuming its signal and clearing the waiting flag
     * before calling the complete real event-task callback. */
    scheduler_signal_full = false;
    callback_pending = false;
    scheduled_callback();
    CHECK(callbacks_seen == 1 && !queue_pending);
    CHECK(locks[0].held == 0);
    CHECK(EventCallbackDispatch(&event, observed_event) == pdTRUE);
    CHECK(callback_dispatches == 3 && callback_pending && scheduler_signal_full);
    scheduler_signal_full = false;
    callback_pending = false;
    scheduled_callback();
    CHECK(callbacks_seen == 2 && !queue_pending && locks[0].held == 0);

    /* Real alarm transitions keep their strict >1000ms decrease grace. */
    now = 2000;
    CHECK(AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_CRITICAL) == 0);
    now = 3000;
    CHECK(AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_OK) == 0);
    CHECK(alarm_data.Alarm.BootFault == SYSTEMALARMS_ALARM_CRITICAL);
    now = 3001;
    CHECK(AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_OK) == 0);
    CHECK(alarm_data.Alarm.BootFault == SYSTEMALARMS_ALARM_OK);
    CHECK(AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_CRITICAL) == 0);
    CHECK(alarm_data.Alarm.BootFault == SYSTEMALARMS_ALARM_CRITICAL);
    CHECK(locks[1].held == 0);
    return 0;
}
