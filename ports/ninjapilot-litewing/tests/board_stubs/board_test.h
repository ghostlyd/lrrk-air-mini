#pragma once
/* Host declarations only. Service implementations live in board_startup_test.c.
 * Generated object layouts and accessor code are the real pinned declarations. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void *xQueueHandle;
#define PIOS_STATIC_ASSERT(x) assert(x)
#include <uavobjectmanager.h>
#include <alarms.h>
#include "pios_board.h"

struct pios_esp32_led { int pin; bool active_low; };
struct pios_esp32_led_cfg { const struct pios_esp32_led *leds; uint8_t num_leds; };
struct pios_esp32_usart_cfg {
    int port, rx_pin, tx_pin;
    uint32_t init_baud;
    uint16_t rx_buffer_size, tx_buffer_size;
    bool invert_rx;
};
/* Opaque driver tokens; the production board passes their addresses only. */
struct pios_com_driver { int token; };
struct pios_rcvr_driver { int token; };
extern const struct pios_com_driver pios_esp32_usart_com_driver;
extern const struct pios_rcvr_driver pios_gcsrcvr_rcvr_driver;
enum { GPIO_NUM_7 = 7, GPIO_NUM_8 = 8, GPIO_NUM_43 = 43, GPIO_NUM_44 = 44, UART_NUM_0 = 0 };
int32_t PIOS_DELAY_Init(void);
int32_t PIOS_LED_Init(const struct pios_esp32_led_cfg *);
void PIOS_LED_On(uint32_t);
int32_t PIOS_TASK_MONITOR_Initialize(uint16_t);
int32_t PIOS_CALLBACKSCHEDULER_Initialize(void);
int32_t EventDispatcherInitialize(void);
int32_t PIOS_ESP32_FLASHFS_Init(uintptr_t *);
void PIOS_DEBUGLOG_Initialize(void);
uint16_t PIOS_WDG_Init(void);
int32_t PIOS_ESP32_USART_Init(uint32_t *, const struct pios_esp32_usart_cfg *);
void *pios_malloc(size_t);
void pios_free(void *);
int32_t PIOS_COM_Init(uint32_t *, const struct pios_com_driver *, uint32_t,
                      uint8_t *, uint16_t, uint8_t *, uint16_t);
int32_t PIOS_GCSRCVR_Init(uint32_t *);
int32_t PIOS_RCVR_Init(uint32_t *, const struct pios_rcvr_driver *, uint32_t);
void PIOS_SYS_Init(void);
unsigned xPortGetFreeHeapSize(void);
void InitModules(void);
int32_t SystemModInitialize(void);
#define MODULE_INITIALISE_ALL do { InitModules(); SystemModInitialize(); } while (0)

/* Deterministic, non-device identity used only by this host fixture. */
#define FW_VERSION_HASH32 0x12345678u
#define FW_VERSION_UNIXTIME 123u
#define FW_VERSION_FWTAG "board-startup-host-test"
#define LRRK_WRAPPER_COMMIT "0123456789abcdef0123456789abcdef01234567"
#define LRRK_WRAPPER_IDENTITY_MARKER "LRRK0123456789abcdef"
#define LRRK_WRAPPER_IDENTITY_MARKER_LENGTH 20u
static const uint8_t fw_version_uavo_sha1[20] = {0};
