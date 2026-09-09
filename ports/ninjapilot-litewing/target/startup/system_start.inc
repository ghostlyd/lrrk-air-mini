/* The boot caller transfers the unpublished persistence queue to System
 * only when task creation succeeds. No creator-side handle registration:
 * the task can execute, fail and delete itself before xTaskCreate returns. */
static void releaseSystemQueue(void)
{
    if (objectPersistenceQueue) {
        vQueueDelete(objectPersistenceQueue);
        objectPersistenceQueue = NULL;
    }
    systemResourcesReady = false;
}

/* Only used before System connects its queue/callbacks to other services. */
static void stopSystemBeforeConnections(bool registered)
{
    PIOS_LiteWing_BrushedPWM_Shutdown();
    AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_CRITICAL);
    releaseSystemQueue();
    if (registered && PIOS_TASK_MONITOR_UnregisterTask(TASKINFO_RUNNING_SYSTEM) != 0) {
        /* Do not turn a still-published monitor handle into a dangling one.
         * Outputs remain latched off; no more startup/monitoring work runs. */
        for (;;) {
            vTaskDelay(portMAX_DELAY);
        }
    }
    vTaskDelete(NULL);
}

int32_t SystemModStart(void)
{
    /* These entry points are boot-caller-only, not a concurrent start API. */
    if (!systemResourcesReady || systemStartAttempted) {
        return -1;
    }
    systemStartAttempted = true;
    stackOverflow = STACKOVERFLOW_NONE;
    mallocFailed = false;
    /* Preserve the shared stack-in-words contract; the ESP32 shim converts
     * to bytes once. The task owns its current handle and monitor slot. */
    if (xTaskCreate(systemTask, "System", STACK_SIZE_BYTES / 4, NULL,
                    TASK_PRIORITY, NULL) != pdPASS) {
        return -1;
    }
    return 0;
}
