/*
 * Explicit module table for ESP-IDF. The Make-based NinjaPilot targets
 * generate this file; the wrapper keeps the selected, rate-mode set checked
 * in so a module cannot disappear silently from a CMake build.
 */
#include <pios_litewing_modules.h>
#include <stdbool.h>

static bool initAttempted, initialized, startAttempted;

extern int32_t AttitudeInitialize(void);
extern int32_t StabilizationInitialize(void);
extern int32_t ActuatorInitialize(void);
extern int32_t ReceiverInitialize(void);
extern int32_t ManualControlInitialize(void);
extern int32_t TelemetryInitialize(void);
extern int32_t LiteWingBatteryInitialize(void);

extern int32_t AttitudeStart(void);
extern int32_t StabilizationStart(void);
extern int32_t ActuatorStart(void);
extern int32_t ReceiverStart(void);
extern int32_t ManualControlStart(void);
extern int32_t TelemetryStart(void);
extern int32_t LiteWingBatteryStart(void);

#define CHECK_MODULE(call) do { int32_t rc = (call); if (rc != 0) return rc; } while (0)

int32_t PIOS_LiteWing_ModulesInitialize(void)
{
    if (initAttempted) return -1;
    initAttempted = true;
    CHECK_MODULE(AttitudeInitialize());
    CHECK_MODULE(StabilizationInitialize());
    CHECK_MODULE(ActuatorInitialize());
    CHECK_MODULE(ReceiverInitialize());
    CHECK_MODULE(ManualControlInitialize());
    CHECK_MODULE(TelemetryInitialize());
    CHECK_MODULE(LiteWingBatteryInitialize());
    initialized = true;
    return 0;
}

int32_t PIOS_LiteWing_ModulesStart(void)
{
    if (!initialized || startAttempted) return -1;
    startAttempted = true;
    CHECK_MODULE(AttitudeStart());
    CHECK_MODULE(StabilizationStart());
    CHECK_MODULE(ActuatorStart());
    CHECK_MODULE(ReceiverStart());
    CHECK_MODULE(ManualControlStart());
    CHECK_MODULE(TelemetryStart());
    CHECK_MODULE(LiteWingBatteryStart());
    return 0;
}
