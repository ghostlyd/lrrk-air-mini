#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef void *UAVObjHandle;
typedef enum { EV_UNPACKED=1, EV_UPDATED=2, EV_UPDATED_MANUAL=4,
               EV_UPDATED_PERIODIC=8, EV_LOGGING_MANUAL=16,
               EV_LOGGING_PERIODIC=32, EV_UPDATE_REQ=64 } UAVObjEventType;
typedef struct { UAVObjHandle obj; uint16_t instId; UAVObjEventType event;
                 bool lowPriority; } UAVObjEvent;
typedef void (*UAVObjEventCallback)(UAVObjEvent *);
int32_t UAVObjUnpack(UAVObjHandle, uint16_t, const uint8_t *);
