/* SPDX-License-Identifier: GPL-3.0-or-later
 * Checked counterpart of the pinned OpenPilot persistence delete boundary.
 * Copyright (C) 2026 LRRK contributors.
 */
#include "pios.h"
#include "uavobjectmanager.h"
#include "pios_flashfs.h"

extern uintptr_t pios_uavo_settings_fs_id;
const int litewing_checked_delete_linked = 1;

int32_t UAVObjDelete(UAVObjHandle obj, uint16_t instance)
{
    PIOS_Assert(obj);
    return PIOS_FLASHFS_ObjDelete(pios_uavo_settings_fs_id, UAVObjGetID(obj), instance);
}
