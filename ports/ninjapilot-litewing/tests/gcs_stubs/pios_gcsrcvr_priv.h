#pragma once
#include "pios.h"
#define GCSRECEIVER_CHANNEL_NUMELEM 8
typedef struct { uint16_t Channel[8]; } GCSReceiverData;
UAVObjHandle GCSReceiverHandle(void);
int32_t GCSReceiverGet(GCSReceiverData *);
int32_t GCSReceiverConnectCallback(UAVObjEventCallback);
int32_t PIOS_GCSRCVR_Init(uint32_t *);
extern const struct pios_rcvr_driver pios_gcsrcvr_rcvr_driver;
