#ifndef PIOS_LITEWING_BATTERY_H
#define PIOS_LITEWING_BATTERY_H
#include "litewing_battery_voltage.h"
/* Single, non-migrating worker owns both entry points. Init attempts once.
 * Successful handles live for the worker lifetime. No ISR-side calibration.
 */
int PIOS_LiteWing_BatteryADC_Init(void);
bool PIOS_LiteWing_BatteryADC_Read(struct litewing_battery_sample *sample);
#endif
