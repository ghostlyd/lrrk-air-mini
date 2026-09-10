/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "pios.h"
#include "pios_litewing_gcsrcvr.h"

extern int32_t UAVObjLoad_unserialized(UAVObjHandle obj, uint16_t instance);

int32_t UAVObjLoad(UAVObjHandle obj, uint16_t instance)
{
    return PIOS_LiteWing_GCSReceiver_SettingsLoad(obj,instance,UAVObjLoad_unserialized);
}
