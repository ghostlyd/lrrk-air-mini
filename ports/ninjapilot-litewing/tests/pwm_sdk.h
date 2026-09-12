#ifndef PWM_SDK_H
#define PWM_SDK_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
typedef void *UAVObjHandle;
typedef struct { unsigned access; } UAVObjMetadata;
enum { ACCESS_READONLY = 1 };
uint32_t UAVObjGetID(UAVObjHandle);
uint16_t UAVObjGetNumBytes(UAVObjHandle);
unsigned UAVObjGetGcsAccess(const UAVObjMetadata *);
int64_t esp_timer_get_time(void);
int32_t UAVObjPack(UAVObjHandle, uint16_t, uint8_t *);
typedef unsigned portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(lock) ((void)(lock))
#define portEXIT_CRITICAL(lock) ((void)(lock))
#endif
