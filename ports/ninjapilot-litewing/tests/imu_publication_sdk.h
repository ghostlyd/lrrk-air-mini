#ifndef IMU_PUBLICATION_SDK_H
#define IMU_PUBLICATION_SDK_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <assert.h>
#include <pthread.h>
#define PIOS_INCLUDE_I2C 1
#define IRAM_ATTR
#define PIOS_Assert assert
#define PIOS_CONST_MKS_GRAV_ACCEL_F 9.81f
typedef pthread_mutex_t portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED PTHREAD_MUTEX_INITIALIZER
#define portENTER_CRITICAL(m) pthread_mutex_lock(m)
#define portEXIT_CRITICAL(m) pthread_mutex_unlock(m)
typedef void *QueueHandle_t;
typedef void *TaskHandle_t;
typedef int BaseType_t;
typedef int esp_err_t;
enum { pdTRUE=1, pdFALSE=0, pdPASS=1, tskIDLE_PRIORITY=0, portTICK_PERIOD_MS=1,
       ESP_OK=0, ESP_ERR_INVALID_STATE=2, ESP_INTR_FLAG_IRAM=1,
       GPIO_MODE_INPUT=0, GPIO_PULLUP_DISABLE=0, GPIO_PULLDOWN_DISABLE=0,
       GPIO_INTR_POSEDGE=1, PIOS_I2C_TXN_WRITE=0, PIOS_I2C_TXN_READ=1,
       PIOS_SENSORS_TYPE_3AXIS_GYRO_ACCEL=1 };
#define pdMS_TO_TICKS(ms) (ms)
#define portYIELD_FROM_ISR() ((void)0)
typedef struct { int16_t x,y,z; } Vector3i16;
typedef struct { int16_t temperature; uint8_t count; Vector3i16 sample[]; } PIOS_SENSORS_3Axis_SensorsWithTemp;
typedef struct { uint64_t pin_bit_mask; int mode,pull_up_en,pull_down_en,intr_type; } gpio_config_t;
struct pios_i2c_txn { const char *info; uint8_t addr; int rw; uint32_t len; uint8_t *buf; };
typedef struct {
 bool (*test)(uintptr_t); void *poll,*fetch; void (*reset)(uintptr_t);
 QueueHandle_t (*get_queue)(uintptr_t); void (*get_scale)(float *,uint8_t,uintptr_t);
 bool is_polled;
} PIOS_SENSORS_Driver;
int PIOS_I2C_Transfer(uint32_t,const struct pios_i2c_txn *,unsigned);
bool PIOS_ESP32_I2C_Probe(uint32_t,uint8_t);
int PIOS_SENSORS_Register(const PIOS_SENSORS_Driver *,int,uintptr_t);
void *pios_malloc(size_t);
int xQueueSend(void *,const void *,unsigned);
int xQueueReceive(void *,void *,unsigned);
void *xQueueCreate(unsigned,unsigned);
void vQueueDelete(void *);
void vTaskDelay(unsigned);
void vTaskNotifyGiveFromISR(void *,int *);
uint32_t ulTaskNotifyTake(int,unsigned);
uint32_t xTaskGetTickCount(void);
int xTaskCreate(void (*)(void *),const char *,unsigned,void *,unsigned,void **);
int gpio_config(const gpio_config_t *);
int gpio_install_isr_service(int);
int gpio_isr_handler_add(int,void (*)(void *),void *);
int64_t esp_timer_get_time(void);
typedef void *UAVObjHandle;
typedef struct { unsigned flags; unsigned telemetryUpdatePeriod; } UAVObjMetadata;
enum { UPDATEMODE_ONCHANGE=2, ACCESS_READONLY=1 };
#define LITEWINGIMUHEALTH_OBJID 0xDA60A0C6u
typedef struct __attribute__((packed)) { uint32_t SampleAgeMs; uint8_t Version,IdentityVerified,WhoAmI,SampleSeen,Health; } LiteWingIMUHealthData;
int32_t LiteWingIMUHealthInitialize(void);
UAVObjHandle LiteWingIMUHealthHandle(void);
int LiteWingIMUHealthSet(const LiteWingIMUHealthData *);
int LiteWingIMUHealthGetMetadata(UAVObjMetadata *);
int LiteWingIMUHealthSetMetadata(const UAVObjMetadata *);
void UAVObjSetTelemetryUpdateMode(UAVObjMetadata *,int);
unsigned UAVObjGetGcsAccess(const UAVObjMetadata *);
uint32_t UAVObjGetID(UAVObjHandle);
uint16_t UAVObjGetNumBytes(UAVObjHandle);
int32_t UAVObjPack(UAVObjHandle,uint16_t,uint8_t *);
int xTaskCreatePinnedToCore(void (*)(void *),const char *,unsigned,void *,unsigned,void *,int);
#endif
