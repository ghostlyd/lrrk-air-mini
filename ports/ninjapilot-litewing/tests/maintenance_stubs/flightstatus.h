#pragma once
#include <stdint.h>
/* Complete data layout from pinned flightstatus.xml; generated-header target
 * compilation separately checks this boundary against the real UAVObject API. */
typedef struct { uint8_t Stabilization, PathFollower, PathPlanner; } FlightStatusControlChainData;
typedef struct {
    uint8_t Armed, FlightMode, FlightModeAssist, AssistedControlState, AssistedThrottleState;
    FlightStatusControlChainData ControlChain;
} FlightStatusData;
#define FLIGHTSTATUS_ARMED_DISARMED 0
#define FLIGHTSTATUS_ARMED_ARMED 2
int32_t FlightStatusGet(FlightStatusData *out);
