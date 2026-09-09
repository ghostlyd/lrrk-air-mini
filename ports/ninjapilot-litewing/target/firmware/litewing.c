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

    /* USE_ESP32 maps this macro to the checked-in module table and the
     * System module initializer. StartModules is called by SystemModStart. */
    MODULE_INITIALISE_ALL;

    printf("[NinjaPilot] LiteWing init complete, %u bytes heap free\n",
           (unsigned)xPortGetFreeHeapSize());
}
