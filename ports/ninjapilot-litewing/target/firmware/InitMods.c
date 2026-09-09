/*
 * Explicit module table for ESP-IDF. The Make-based NinjaPilot targets
 * generate this file; the wrapper keeps the selected, rate-mode set checked
 * in so a module cannot disappear silently from a CMake build.
 */
extern unsigned int AttitudeInitialize(void);
extern unsigned int StabilizationInitialize(void);
extern unsigned int ActuatorInitialize(void);
extern unsigned int ReceiverInitialize(void);
extern unsigned int ManualControlInitialize(void);
extern unsigned int TelemetryInitialize(void);

extern unsigned int AttitudeStart(void);
extern unsigned int StabilizationStart(void);
extern unsigned int ActuatorStart(void);
extern unsigned int ReceiverStart(void);
extern unsigned int ManualControlStart(void);
extern unsigned int TelemetryStart(void);

void InitModules(void)
{
    AttitudeInitialize();
    StabilizationInitialize();
    ActuatorInitialize();
    ReceiverInitialize();
    ManualControlInitialize();
    TelemetryInitialize();
}

void StartModules(void)
{
    AttitudeStart();
    StabilizationStart();
    ActuatorStart();
    ReceiverStart();
    ManualControlStart();
    TelemetryStart();
}
