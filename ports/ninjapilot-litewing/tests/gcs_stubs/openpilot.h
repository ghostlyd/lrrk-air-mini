#pragma once
#include "pios.h"
#include "uavobjectmanager.h"
#include "uavtalk.h"
#include <string.h>
#define pdTRUE 1
#define pdFALSE 0
#define portMAX_DELAY UINT32_MAX
#define portTICK_RATE_MS 1
#define UAVOBJ_ALL_INSTANCES UINT16_MAX
typedef uint32_t portTickType;
void *xSemaphoreCreateRecursiveMutex(void);
int xSemaphoreTakeRecursive(void *, uint32_t);
int xSemaphoreGiveRecursive(void *);
int xSemaphoreTake(void *, uint32_t);
int xSemaphoreGive(void *);
#define vSemaphoreCreateBinary(s) ((s)=xSemaphoreCreateRecursiveMutex())
uint32_t xTaskGetTickCount(void);
UAVObjHandle UAVObjGetByID(uint32_t);
uint32_t UAVObjGetID(UAVObjHandle);
uint16_t UAVObjGetNumBytes(UAVObjHandle);
uint16_t UAVObjGetNumInstances(UAVObjHandle);
bool UAVObjIsSingleInstance(UAVObjHandle);
int32_t UAVObjPack(UAVObjHandle,uint16_t,uint8_t *);
uint8_t PIOS_CRC_updateByte(uint8_t,uint8_t);
uint8_t PIOS_CRC_updateCRC(uint8_t,const uint8_t *,int32_t);
