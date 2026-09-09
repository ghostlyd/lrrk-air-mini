/* Boot-caller-only lifecycle, not a concurrent or restartable API.
 * Success means resources/task creation accepted, not worker/flight ready. */
int32_t ActuatorStart(void)
{
    if (!actuatorResourcesReady || actuatorStartAttempted) return -1;
    actuatorStartAttempted = true;
#ifdef PIOS_INCLUDE_WDG
    /* Register from the serialized startup caller before this worker can
     * update its flag. A later task-create failure aborts boot; no retry. */
    if (!PIOS_WDG_RegisterFlag(PIOS_WDG_ACTUATOR)) return -1;
#endif
    if (xTaskCreate(actuatorTask, "Actuator", STACK_SIZE_BYTES / 4, NULL,
                    TASK_PRIORITY, NULL) != pdPASS) return -1;
    return 0;
}

int32_t ActuatorInitialize(void)
{
    if (actuatorInitAttempted) return -1;
    actuatorInitAttempted = true;
    /* Other initializers may own these global objects already. Never
     * reinitialize defaults or free shared objects on a later failure. */
    if (!ActuatorSettingsHandle() && (ActuatorSettingsInitialize() != 0 || !ActuatorSettingsHandle())) return -1;
    if (!MixerSettingsHandle() && (MixerSettingsInitialize() != 0 || !MixerSettingsHandle())) return -1;
    if (!ActuatorDesiredHandle() && (ActuatorDesiredInitialize() != 0 || !ActuatorDesiredHandle())) return -1;
    if (!AccessoryDesiredHandle() && (AccessoryDesiredInitialize() != 0 || !AccessoryDesiredHandle())) return -1;
    if (!ActuatorCommandHandle() && (ActuatorCommandInitialize() != 0 || !ActuatorCommandHandle())) return -1;
#ifdef DIAG_MIXERSTATUS
    if (!MixerStatusHandle() && (MixerStatusInitialize() != 0 || !MixerStatusHandle())) return -1;
#endif
#ifndef PIOS_EXCLUDE_ADVANCED_FEATURES
    if (!VtolPathFollowerSettingsHandle() && (VtolPathFollowerSettingsInitialize() != 0 || !VtolPathFollowerSettingsHandle())) return -1;
#endif
    if (!SystemSettingsHandle() && (SystemSettingsInitialize() != 0 || !SystemSettingsHandle())) return -1;

    /* Successful subscriptions to static callbacks remain valid if a later
     * step fails. The checked module caller aborts boot on any failure. */
    if (ActuatorSettingsConnectCallback(ActuatorSettingsUpdatedCb) != 0) return -1;
    if (MixerSettingsConnectCallback(MixerSettingsUpdatedCb) != 0) return -1;
#ifndef PIOS_EXCLUDE_ADVANCED_FEATURES
    if (VtolPathFollowerSettingsConnectCallback(&SettingsUpdatedCb) != 0) return -1;
#endif
    if (SystemSettingsConnectCallback(&SettingsUpdatedCb) != 0) return -1;

    /* Publish last: allocation or subscription failure cannot leave a
     * dangling queue reference. A connected queue lives until reboot. */
    queue = xQueueCreate(MAX_QUEUE_SIZE, sizeof(UAVObjEvent));
    if (!queue) return -1;
    if (ActuatorDesiredConnectQueue(queue) != 0) {
        vQueueDelete(queue);
        queue = NULL;
        return -1;
    }
    actuatorResourcesReady = true;
    return 0;
}
