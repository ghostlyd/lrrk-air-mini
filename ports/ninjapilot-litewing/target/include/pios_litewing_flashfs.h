/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 LRRK contributors. */
#pragma once
#include <stdbool.h>
#include <stdint.h>

/* Present=1, confirmed absent=0, incompatible or I/O error=-1. */
int32_t PIOS_LiteWing_FLASHFS_ObjectState(uintptr_t, uint32_t, uint16_t, uint16_t);
bool PIOS_LiteWing_FLASHFS_Healthy(void);
int32_t PIOS_LiteWing_FLASHFS_MarkProvisioned(void);
