#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <assert.h>
#define PIOS_INCLUDE_GCSRCVR
#define PIOS_INCLUDE_FREERTOS
#define pios_malloc malloc
#define PIOS_Assert assert
typedef void *xSemaphoreHandle;
struct pios_rcvr_driver {
    void (*init)(uint32_t);
    int32_t (*read)(uint32_t, uint8_t);
    xSemaphoreHandle (*get_semaphore)(uint32_t, uint8_t);
};
enum { PIOS_RCVR_TIMEOUT = -1, PIOS_RCVR_INVALID = -2, PIOS_RCVR_NODRIVER = -3 };
