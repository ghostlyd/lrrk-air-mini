/* ESP-IDF entry point. IDF has already started FreeRTOS before app_main. */
#include "inc/openpilot.h"

#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <systemmod.h>
#include <pios_litewing_brushed_pwm.h>
#include <pios_litewing_modules.h>

extern void PIOS_Board_Init(void);

void app_main(void)
{
    PIOS_SYS_Init();
    printf("[NinjaPilot] LiteWing V2.6.C target starting\n");

    PIOS_Board_Init();
    if (!PIOS_LiteWing_BoardServicesInitialized()) {
        printf("[LiteWing] board startup failed; modules not initialized\n");
        return;
    }

    if (PIOS_LiteWing_ModulesInitialize() != 0) {
        PIOS_LiteWing_BrushedPWM_Shutdown();
        AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_CRITICAL);
        printf("[LiteWing] module initialization failed\n");
        return;
    }
    if (SystemModInitialize() != 0) {
        PIOS_LiteWing_BrushedPWM_Shutdown();
        AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_CRITICAL);
        printf("[LiteWing] System initialization failed\n");
        return;
    }

    /* The System task may not have run yet; this is not boot readiness. */
    printf("[NinjaPilot] LiteWing module startup requested, %u bytes heap free\n",
           (unsigned)xPortGetFreeHeapSize());
}
