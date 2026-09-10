/* Boot-caller-only lifecycle, not a concurrent or restartable API.
 * Success means the initial callback is pending, not that it has run. */
int32_t ManualControlStart(void)
{
    if (!manualControlResourcesReady || manualControlStartAttempted) return -1;
    manualControlStartAttempted = true;

    if (configuration_check() != 0) return -1;
    if (SystemSettingsConnectCallback(configurationUpdatedCb) != 0) return -1;
    if (ManualControlSettingsConnectCallback(configurationUpdatedCb) != 0) return -1;
    if (ManualControlCommandConnectCallback(commandUpdatedCb) != 0) return -1;
    if (AlarmsClear(SYSTEMALARMS_ALARM_MANUALCONTROL) != 0) return -1;

    SettingsUpdatedCb(NULL);
    armHandler(true, frameType);
#ifndef PIOS_EXCLUDE_ADVANCED_FEATURES
    takeOffLocationHandlerInit();
#endif

    /* Create gives a new scheduler worker an initially-full binary signal.
     * Dispatch still marks this callback waiting, but therefore returns zero
     * before scheduler start. The real scheduler test proves later execution. */
    (void)PIOS_CALLBACKSCHEDULER_Dispatch(callbackHandle);
    return 0;
}
