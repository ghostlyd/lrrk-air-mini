/* ESP-IDF entry point. IDF has already started FreeRTOS before app_main. */
#include "inc/openpilot.h"

#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <systemmod.h>

extern void PIOS_Board_Init(void);
extern void InitModules(void);
extern void StartModules(void);

void app_main(void)
{
    PIOS_SYS_Init();
    printf("[NinjaPilot] LiteWing V2.6.C target starting\n");

    PIOS_Board_Init();
    if (!PIOS_LiteWing_BoardServicesInitialized()) {
        printf("[LiteWing] board startup failed; modules not initialized\n");
        return;
    }

    /* USE_ESP32 maps this macro to the checked-in module table and the
     * System module initializer. StartModules runs later inside System's task;
     * returning here does not prove that asynchronous startup has succeeded. */
    MODULE_INITIALISE_ALL;

    printf("[NinjaPilot] LiteWing module startup requested, %u bytes heap free\n",
           (unsigned)xPortGetFreeHeapSize());
}
