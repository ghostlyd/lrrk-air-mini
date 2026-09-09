#ifndef LRRK_PIOS_LITEWING_BRUSHED_PWM_H
#define LRRK_PIOS_LITEWING_BRUSHED_PWM_H

#include <stdbool.h>
#include <stdint.h>

int32_t PIOS_LiteWing_BrushedPWM_Init(void);
void PIOS_LiteWing_BrushedPWM_SetImuHealthy(bool healthy);
void PIOS_LiteWing_BrushedPWM_SetFailsafe(bool failsafe);
void PIOS_LiteWing_BrushedPWM_Shutdown(void);

#endif /* LRRK_PIOS_LITEWING_BRUSHED_PWM_H */
