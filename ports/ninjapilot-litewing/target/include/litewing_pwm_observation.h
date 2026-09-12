#ifndef LITEWING_PWM_OBSERVATION_H
#define LITEWING_PWM_OBSERVATION_H
#include "uavobjectmanager.h"
/* This bounds snapshot acquisition-to-pack age, NOT output-command age.
 * Driver output freshness is reported independently in suppression bit 2. */
#define LITEWING_PWM_OBSERVATION_MAX_AGE_US 100000
int32_t LiteWingPwmObservationInitialize(void);
int32_t LiteWingPwmObservationPack(UAVObjHandle obj, uint16_t instance, uint8_t *data);
#endif
