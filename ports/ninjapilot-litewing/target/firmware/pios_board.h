/* Board-level constants and handles for LiteWing V2.6.C. */
#ifndef LRRK_LITEWING_PIOS_BOARD_H
#define LRRK_LITEWING_PIOS_BOARD_H

#include <stdint.h>

#define PIOS_LED_HEARTBEAT             0
#define PIOS_LED_ALARM                 1
#define PIOS_LED_NUM                   2

#define PIOS_WATCHDOG_TIMEOUT          250
#define PIOS_WDG_ACTUATOR              0x0001
#define PIOS_WDG_STABILIZATION         0x0002
#define PIOS_WDG_ATTITUDE              0x0004
#define PIOS_WDG_MANUAL                0x0008

#define PIOS_RCVR_MAX_CHANNELS         12
#define PIOS_RCVR_MAX_DEVS             2
#define PIOS_GCSRCVR_MAX_DEVS          1

#define PIOS_SERVO_MAX_BANKS           1
#define PIOS_SERVOS_INITIAL_POSITION   0

#define PIOS_COM_MAX_DEVS              2
#define PIOS_COM_TELEM_RF_RX_BUF_LEN   2048
#define PIOS_COM_TELEM_RF_TX_BUF_LEN   512
#define PIOS_COM_TELEM_RF              (pios_com_telem_rf_id)
#define TELEM_QUEUE_SIZE               20

/* PiOS stores these in bytes and the ESP32 shim converts task depth to IDF's
 * byte-counted stack size. */
#define PIOS_ATTITUDE_STACK_SIZE       4096
#define PIOS_STABILIZATION_STACK_SIZE  4096
#define PIOS_ACTUATOR_STACK_SIZE       4096
#define PIOS_RECEIVER_STACK_SIZE       3072
#define PIOS_MANUAL_STACK_SIZE         3072
#define PIOS_SYSTEM_STACK_SIZE         4096
#define PIOS_EVENTDISPATCHER_STACK_SIZE 4096
#define PIOS_TELEM_STACK_SIZE          8192

extern uint32_t pios_com_telem_rf_id;
extern uint32_t pios_com_aux_id;

#endif
