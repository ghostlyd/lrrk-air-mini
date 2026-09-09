#pragma once
#include <stdint.h>
typedef void *UAVObjHandle;
uint32_t UAVObjGetID(UAVObjHandle);
int32_t UAVObjDelete(UAVObjHandle, uint16_t);
