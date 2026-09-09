/* The caller holds the recursive scheduler mutex. New workers cannot enter
 * a callback until it is released; a failed batch can delete its workers. */
static int32_t startSchedulerTask(struct DelayedCallbackTaskStruct *task, int index)
{
    if (xTaskCreate(CallbackSchedulerTask, task->name,
                   1 + (task->stackSize / 4), task, task->priorityTask,
                   &task->callbackSchedulerTaskHandle) != pdPASS) {
        return -1;
    }
    if (TASKINFO_RUNNING_CALLBACKSCHEDULER0 + index <= TASKINFO_RUNNING_CALLBACKSCHEDULER3) {
        if (PIOS_TASK_MONITOR_RegisterTask(TASKINFO_RUNNING_CALLBACKSCHEDULER0 + index,
                                         task->callbackSchedulerTaskHandle) != 0) {
            vTaskDelete(task->callbackSchedulerTaskHandle);
            task->callbackSchedulerTaskHandle = NULL;
            return -1;
        }
        task->monitorRegistered = true;
    }
    return 0;
}

static void stopSchedulerTask(struct DelayedCallbackTaskStruct *task, int index)
{
    if (task->monitorRegistered) {
        PIOS_TASK_MONITOR_UnregisterTask(TASKINFO_RUNNING_CALLBACKSCHEDULER0 + index);
        task->monitorRegistered = false;
    }
    if (task->callbackSchedulerTaskHandle) {
        vTaskDelete(task->callbackSchedulerTaskHandle);
        task->callbackSchedulerTaskHandle = NULL;
    }
}

int32_t PIOS_CALLBACKSCHEDULER_Start()
{
    xSemaphoreTakeRecursive(mutex, portMAX_DELAY);
    if (schedulerStartAttempted) {
        xSemaphoreGiveRecursive(mutex);
        return -1;
    }
    schedulerStartAttempted = true;

    struct DelayedCallbackTaskStruct *cursor = NULL;
    int index = 0;
    LL_FOREACH(schedulerTasks, cursor) {
        if (startSchedulerTask(cursor, index) != 0) {
            /* Keep published callback handles allocated, but remove all
             * workers before releasing the gate. Failure cannot retry. */
            int cleanup_index = 0;
            struct DelayedCallbackTaskStruct *cleanup = NULL;
            LL_FOREACH(schedulerTasks, cleanup) {
                stopSchedulerTask(cleanup, cleanup_index++);
            }
            xSemaphoreGiveRecursive(mutex);
            return -1;
        }
        index++;
    }
    schedulerStarted = true;
    xSemaphoreGiveRecursive(mutex);
    return 0;
}
