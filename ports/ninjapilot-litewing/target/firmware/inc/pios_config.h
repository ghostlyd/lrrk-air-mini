/*
 * PiOS feature selection for the LiteWing V2.6.C ESP32-S3 target.
 *
 * This first hardware image is rate-mode-only. Wi-Fi, navigation, Remote ID,
 * physical RC protocols, and position sensors stay out until their own
 * source and bench gates exist. The host AI assistant is never compiled here.
 */
#ifndef LRRK_LITEWING_PIOS_CONFIG_H
#define LRRK_LITEWING_PIOS_CONFIG_H

#define PIOS_ESP32_LITEWING

/* Core services. */
#define PIOS_INCLUDE_FREERTOS
#define PIOS_INCLUDE_CALLBACKSCHEDULER
#define PIOS_INCLUDE_TASK_MONITOR
#define PIOS_INCLUDE_INITCALL
#define PIOS_INCLUDE_DELAY
#define PIOS_INCLUDE_SYS
#define PIOS_INCLUDE_IRQ
#define PIOS_INCLUDE_LED
#define PIOS_INCLUDE_WDG

/* UART/UAVTalk, GCS receiver, settings persistence, and brushed outputs. */
#define PIOS_INCLUDE_COM
#define PIOS_INCLUDE_COM_TELEM
#define PIOS_INCLUDE_USART
#define PIOS_INCLUDE_I2C
#define PIOS_INCLUDE_SERVO
#define PIOS_INCLUDE_RCVR
#define PIOS_INCLUDE_GCSRCVR
#define PIOS_INCLUDE_FLASH

/* The selected flight tree uses this symbol to select the ESP32 sensor path.
 * The LiteWing adapter provides the symbol and MPU6050-over-I2C behavior. */
#define PIOS_INCLUDE_ICM20602

#define PIOS_SENSOR_RATE               500.0f
#define PIOS_QUATERNION_STABILIZATION

/* Conservative first-bring-up thresholds. */
#define HEAP_LIMIT_WARNING             16000
#define HEAP_LIMIT_CRITICAL            8000
#define IRQSTACK_LIMIT_WARNING         150
#define IRQSTACK_LIMIT_CRITICAL        80
#define CPULOAD_LIMIT_WARNING          80
#define CPULOAD_LIMIT_CRITICAL         95

#endif
