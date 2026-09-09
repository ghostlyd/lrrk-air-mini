#pragma once
#include <stdint.h>
struct PIOS_FLASHFS_Stats { uint16_t num_active_slots, num_free_slots; };
int32_t PIOS_ESP32_FLASHFS_Init(uintptr_t *);
int32_t PIOS_FLASHFS_ObjSave(uintptr_t, uint32_t, uint16_t, uint8_t *, uint16_t);
int32_t PIOS_FLASHFS_ObjLoad(uintptr_t, uint32_t, uint16_t, uint8_t *, uint16_t);
int32_t PIOS_FLASHFS_ObjDelete(uintptr_t, uint32_t, uint16_t);
int32_t PIOS_FLASHFS_Format(uintptr_t);
