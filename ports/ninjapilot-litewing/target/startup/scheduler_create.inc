DelayedCallbackInfo *PIOS_CALLBACKSCHEDULER_Create(
    DelayedCallback cb,
    DelayedCallbackPriority priority,
    DelayedCallbackPriorityTask priorityTask,
    int16_t callbackID,
    uint32_t stacksize)
{
    xSemaphoreTakeRecursive(mutex, portMAX_DELAY);
    if (schedulerStartAttempted && !schedulerStarted) {
        xSemaphoreGiveRecursive(mutex);
        return NULL;
    }
    stacksize += STACK_SIZE;
    struct DelayedCallbackTaskStruct *task = NULL;
    int index = 0;
    LL_FOREACH(schedulerTasks, task) {
        if (task->priorityTask == priorityTask) break;
        index++;
    }
    bool newTask = task == NULL;
    if (!newTask && schedulerStarted && stacksize > task->stackSize) {
        /* Never inflate the accounting for an already fixed worker stack. */
        xSemaphoreGiveRecursive(mutex);
        return NULL;
    }
    if (newTask) {
        task = pios_malloc(sizeof(*task));
        if (!task) {
            xSemaphoreGiveRecursive(mutex);
            return NULL;
        }
        memset(task, 0, sizeof(*task));
        task->name[0] = 'C';
        task->name[1] = 'a' + index;
        task->stackSize = stacksize;
        task->priorityTask = priorityTask;
        vSemaphoreCreateBinary(task->signal);
        if (!task->signal) {
            pios_free(task);
            xSemaphoreGiveRecursive(mutex);
            return NULL;
        }
    }
    DelayedCallbackInfo *info = pios_malloc(sizeof(*info));
    if (!info) {
        if (newTask) {
            vSemaphoreDelete(task->signal);
            pios_free(task);
        }
        xSemaphoreGiveRecursive(mutex);
        return NULL;
    }
    memset(info, 0, sizeof(*info));
    info->task = task;
    info->cb = cb;
    info->callbackID = callbackID;
    info->stackSize = stacksize - STACK_SIZE;
    info->stackNotFree = info->stackSize;
    info->stackSafetyCount = STACK_SAFETYCOUNT;

    if (newTask && schedulerStarted && startSchedulerTask(task, index) != 0) {
        pios_free(info);
        vSemaphoreDelete(task->signal);
        pios_free(task);
        xSemaphoreGiveRecursive(mutex);
        return NULL;
    }
    if (!schedulerStarted && stacksize > task->stackSize) task->stackSize = stacksize;
    LL_APPEND(task->callbackQueue[priority], info);
    if (newTask) LL_APPEND(schedulerTasks, task);
    xSemaphoreGiveRecursive(mutex);
    return info;
}
