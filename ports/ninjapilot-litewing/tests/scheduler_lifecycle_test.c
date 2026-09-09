#include <pios.h>
#include <uavobjectmanager.h>
#include <taskinfo.h>
#include <stdio.h>
#include <setjmp.h>

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "line %d: %s\n", __LINE__, #c); exit(1); } } while (0)
static const char *scenario;
static unsigned fail_malloc, fail_signal, fail_task, fail_monitor;
static unsigned malloc_calls, signal_calls, task_calls, monitor_calls;
static unsigned live_allocations, live_signals, callback_calls, executing;
static uint32_t now;
static jmp_buf blocked;
static bool may_block;
static struct { void *pointer; bool live; } allocations[32];
static struct sem { bool live, recursive, full; unsigned held, owner; } sems[16];
static unsigned semaphore_count;
static struct task { bool live, monitored; TaskFunction_t entry; void *arg; uint32_t words; uint16_t id; } tasks[16];

void *pios_malloc(size_t size)
{
    unsigned slot = malloc_calls++;
    CHECK(slot < 32);
    if (malloc_calls == fail_malloc) return NULL;
    void *p = malloc(size);
    CHECK(p);
    /* Catch reliance on zeroed allocator memory (e.g. task handles). */
    memset(p, 0xa5, size);
    allocations[slot].pointer = p;
    allocations[slot].live = true;
    live_allocations++;
    return p;
}
void pios_free(void *pointer)
{
    for (unsigned n = 0; n < malloc_calls; n++) {
        if (allocations[n].live && allocations[n].pointer == pointer) {
            allocations[n].live = false;
            live_allocations--;
            free(pointer);
            return;
        }
    }
    CHECK(!"invalid or duplicate allocation free");
}
static struct sem *valid_sem(void *handle)
{
    for (unsigned n = 0; n < semaphore_count; n++)
        if (handle == &sems[n]) { CHECK(sems[n].live); return &sems[n]; }
    CHECK(!"invalid semaphore handle");
    return NULL;
}
xSemaphoreHandle xSemaphoreCreateRecursiveMutex(void)
{
    if (!strcmp(scenario, "mutex")) return NULL;
    CHECK(semaphore_count < 16);
    struct sem *s = &sems[semaphore_count++];
    s->live = s->recursive = true;
    return s;
}
xSemaphoreHandle test_binary_semaphore(void)
{
    if (++signal_calls == fail_signal) return NULL;
    CHECK(semaphore_count < 16);
    struct sem *s = &sems[semaphore_count++];
    s->live = s->full = true;
    live_signals++;
    return s;
}
int xSemaphoreTakeRecursive(void *handle, uint32_t ticks)
{
    struct sem *s = valid_sem(handle);
    CHECK(s->recursive && ticks == portMAX_DELAY);
    if (s->held && s->owner != executing) {
        CHECK(may_block);
        longjmp(blocked, 1);
    }
    s->owner = executing;
    s->held++;
    return pdTRUE;
}
int xSemaphoreGiveRecursive(void *handle)
{
    struct sem *s = valid_sem(handle);
    CHECK(s->recursive && s->held && s->owner == executing);
    s->held--;
    return pdTRUE;
}
int xSemaphoreTake(void *handle, uint32_t ticks)
{
    struct sem *s = valid_sem(handle);
    CHECK(!s->recursive && ticks > 0);
    if (s->full) { s->full = false; return pdTRUE; }
    CHECK(may_block);
    longjmp(blocked, 1);
}
int xSemaphoreGive(void *handle)
{
    struct sem *s = valid_sem(handle);
    CHECK(!s->recursive);
    bool full = s->full;
    s->full = true;
    return full ? 0 : pdTRUE;
}
int xSemaphoreGiveFromISR(void *h, long *wake) { (void)wake; return xSemaphoreGive(h); }
void vSemaphoreDelete(void *handle)
{
    struct sem *s = valid_sem(handle);
    CHECK(s->held == 0);
    if (!s->recursive) live_signals--;
    s->live = false;
}
uint32_t xTaskGetTickCount(void) { return now; }

static void execute_until_block(unsigned n)
{
    CHECK(tasks[n].live && !may_block && executing == 0);
    may_block = true;
    executing = n + 1;
    if (!setjmp(blocked)) tasks[n].entry(tasks[n].arg);
    executing = 0;
    may_block = false;
}
BaseType_t xTaskCreate(TaskFunction_t entry, const char *name, uint32_t words,
                      void *arg, unsigned priority, void **out)
{
    (void)name;
    CHECK(out && arg && priority > 0 && words > 0);
    unsigned n = task_calls++;
    CHECK(n < 16);
    if (task_calls == fail_task) return 0;
    tasks[n] = (struct task){ .live = true, .entry = entry, .arg = arg, .words = words };
    *out = &tasks[n];
    /* Deterministic preemption: a new worker can run immediately. It must
     * block on the real scheduler mutex before executing any callback. */
    unsigned before = callback_calls;
    execute_until_block(n);
    CHECK(callback_calls == before);
    return pdPASS;
}
void vTaskDelete(void *handle)
{
    for (unsigned n = 0; n < task_calls; n++) {
        if (handle == &tasks[n]) { CHECK(tasks[n].live); tasks[n].live = false; return; }
    }
    CHECK(!"invalid task delete");
}
int32_t PIOS_TASK_MONITOR_RegisterTask(uint16_t id, void *handle)
{
    CHECK(id >= TASKINFO_RUNNING_CALLBACKSCHEDULER0 && id <= TASKINFO_RUNNING_CALLBACKSCHEDULER3);
    monitor_calls++;
    for (unsigned n = 0; n < task_calls; n++) {
        if (handle == &tasks[n]) {
            CHECK(tasks[n].live && !tasks[n].monitored);
            if (monitor_calls == fail_monitor) return -1;
            tasks[n].monitored = true;
            tasks[n].id = id;
            return 0;
        }
    }
    CHECK(!"registering invalid task handle");
    return -1;
}
int32_t PIOS_TASK_MONITOR_UnregisterTask(uint16_t id)
{
    for (unsigned n = 0; n < task_calls; n++) {
        if (tasks[n].monitored && tasks[n].id == id) { tasks[n].monitored = false; return 0; }
    }
    CHECK(!"unregistering unowned task slot");
    return -1;
}
static void callback(void) { CHECK(sems[0].held == 0); callback_calls++; }
static DelayedCallbackInfo *create(unsigned priority, unsigned stack)
{
    return PIOS_CALLBACKSCHEDULER_Create(callback, CALLBACK_PRIORITY_REGULAR, priority, 0, stack);
}
static void no_workers(void)
{
    CHECK(sems[0].held == 0 && callback_calls == 0);
    for (unsigned n = 0; n < task_calls; n++) CHECK(!tasks[n].live && !tasks[n].monitored);
}
int main(int argc, char **argv)
{
    CHECK(argc == 2);
    scenario = argv[1];
    if (!strcmp(scenario, "mutex")) { CHECK(PIOS_CALLBACKSCHEDULER_Initialize() == -1); return 0; }
    CHECK(PIOS_CALLBACKSCHEDULER_Initialize() == 0);
    if (!strcmp(scenario, "alloc-task")) fail_malloc = 1;
    if (!strcmp(scenario, "alloc-info")) fail_malloc = 2;
    if (!strcmp(scenario, "signal")) fail_signal = 1;
    if (fail_malloc || fail_signal) {
        CHECK(create(CALLBACK_TASK_FLIGHTCONTROL, 512) == NULL);
        CHECK(live_allocations == 0 && live_signals == 0 && sems[0].held == 0);
        fail_malloc = fail_signal = 0;
        CHECK(create(CALLBACK_TASK_FLIGHTCONTROL, 512));
        CHECK(PIOS_CALLBACKSCHEDULER_Start() == 0 && task_calls == 1);
        return 0;
    }
    DelayedCallbackInfo *first = create(CALLBACK_TASK_FLIGHTCONTROL, 512);
    CHECK(first);
    CHECK(PIOS_CALLBACKSCHEDULER_Dispatch(first) == 0); /* Initially full binary signal. */
    if (!strncmp(scenario, "start-", 6)) {
        CHECK(create(CALLBACK_TASK_AUXILIARY, 512));
        if (!strcmp(scenario, "start-task1")) fail_task = 1;
        if (!strcmp(scenario, "start-task2")) fail_task = 2;
        if (!strcmp(scenario, "start-monitor1")) fail_monitor = 1;
        if (!strcmp(scenario, "start-monitor2")) fail_monitor = 2;
        CHECK(PIOS_CALLBACKSCHEDULER_Start() == -1);
        no_workers();
        unsigned old_tasks = task_calls;
        fail_task = fail_monitor = 0;
        CHECK(PIOS_CALLBACKSCHEDULER_Start() == -1 && task_calls == old_tasks);
        CHECK(create(CALLBACK_TASK_NAVIGATION, 512) == NULL);
        return 0;
    }
    if (!strcmp(scenario, "grow-before-start")) {
        CHECK(create(CALLBACK_TASK_FLIGHTCONTROL, 2048));
        CHECK(PIOS_CALLBACKSCHEDULER_Start() == 0 && task_calls == 1);
        CHECK(tasks[0].words == 562); /* (2048 + 198) / 4 + 1 */
        execute_until_block(0);
        CHECK(callback_calls == 1);
        return 0;
    }
    CHECK(PIOS_CALLBACKSCHEDULER_Start() == 0);
    if (!strcmp(scenario, "late-too-large")) {
        CHECK(create(CALLBACK_TASK_FLIGHTCONTROL, 2048) == NULL);
        CHECK(task_calls == 1 && live_allocations == 2 && live_signals == 1);
    } else if (!strcmp(scenario, "late-normal") || !strcmp(scenario, "late-shared")) {
        bool shared = !strcmp(scenario, "late-shared");
        DelayedCallbackInfo *late = create(shared ? CALLBACK_TASK_FLIGHTCONTROL : CALLBACK_TASK_AUXILIARY, 256);
        CHECK(late);
        CHECK(task_calls == (shared ? 1u : 2u));
        CHECK(live_allocations == (shared ? 3u : 4u) && live_signals == (shared ? 1u : 2u));
        /* Drain the first pending callback, then dispatch the new one. */
        execute_until_block(0);
        CHECK(callback_calls == 1);
        PIOS_CALLBACKSCHEDULER_Dispatch(late);
        execute_until_block(shared ? 0 : 1);
        CHECK(callback_calls == 2 && sems[0].held == 0);
        return 0;
    } else if (!strncmp(scenario, "late-", 5)) {
        if (!strcmp(scenario, "late-task")) fail_task = 2;
        if (!strcmp(scenario, "late-monitor")) fail_monitor = 2;
        if (!strcmp(scenario, "late-info")) fail_malloc = 4;
        CHECK(create(CALLBACK_TASK_AUXILIARY, 512) == NULL);
        CHECK(live_allocations == 2 && live_signals == 1 && sems[0].held == 0);
        for (unsigned n = 1; n < task_calls; n++) CHECK(!tasks[n].live && !tasks[n].monitored);
    }
    execute_until_block(0);
    CHECK(callback_calls == 1);
    CHECK(PIOS_CALLBACKSCHEDULER_Dispatch(first) == pdTRUE);
    execute_until_block(0);
    CHECK(callback_calls == 2 && sems[0].held == 0);
    return 0;
}
