#ifndef LRRK_PIOS_LITEWING_READINESS_H
#define LRRK_PIOS_LITEWING_READINESS_H

#include <stdint.h>

/* Called once by System after every selected module and the callback
 * scheduler report successful startup. Publishes BootFault OK only after
 * the asynchronous flight-critical tasks and first valid IMU sample exist. */
int32_t PIOS_LiteWing_ConfirmBootReady(void);

#endif /* LRRK_PIOS_LITEWING_READINESS_H */
