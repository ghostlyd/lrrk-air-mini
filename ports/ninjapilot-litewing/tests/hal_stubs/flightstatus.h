#pragma once
#include <stdint.h>
#define FLIGHTSTATUS_ARMED_DISARMED 0
#define FLIGHTSTATUS_ARMED_ARMED 2
void FlightStatusArmedGet(uint8_t *armed);
