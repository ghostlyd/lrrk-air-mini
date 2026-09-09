/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LITEWING_GCSRCVR_H
#define LITEWING_GCSRCVR_H
#include <stdint.h>
#include "uavobjectmanager.h"
int32_t PIOS_LiteWing_GCSReceiver_Unpack(UAVObjHandle obj, uint16_t instance,
                                       const uint8_t *data, int64_t received_us);
#endif
