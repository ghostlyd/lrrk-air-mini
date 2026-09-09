/* Generated separately into each selected input module. These are
 * boot-caller-only, one-shot entry points, not a concurrent restart API. */
static void stopInputTask(bool registered)
{
    PIOS_LiteWing_BrushedPWM_Shutdown();
    AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_CRITICAL);
    if (registered && PIOS_TASK_MONITOR_UnregisterTask(INPUT_MONITOR_SLOT) != 0) {
        /* Never leave a monitor pointing at a deleted task. No further
         * input work runs; output shutdown stays latched while parked. */
        for (;;) vTaskDelay(portMAX_DELAY);
    }
    vTaskDelete(NULL);
}

int32_t INPUT_MODULE_START(void)
{
    if (!inputResourcesReady || inputStartAttempted) return -1;
    inputStartAttempted = true;
#ifdef PIOS_INCLUDE_WDG
    /* Register from the serialized boot caller before the worker can run.
     * A later create failure aborts startup; no flag rollback or retry. */
    if (!PIOS_WDG_RegisterFlag(INPUT_WATCHDOG_FLAG)) return -1;
#endif
    if (xTaskCreate(INPUT_TASK_FUNCTION, INPUT_TASK_NAME, STACK_SIZE_BYTES / 4,
                    NULL, TASK_PRIORITY, NULL) != pdPASS) return -1;
    return 0;
}
