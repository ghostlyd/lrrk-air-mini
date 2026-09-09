/*
 * Compatibility boundary for the shared NinjaPilot Attitude module.
 *
 * The selected flight tree uses PIOS_INCLUDE_ICM20602 to select the ESP32
 * sensor-driver branch. LiteWing does not contain an ICM-20602: this header
 * keeps that compile-time branch while the implementation below supplies an
 * MPU6050-over-I2C driver with the same PIOS_SENSORS_Driver queue contract.
 */
#ifndef LRRK_LITEWING_PIOS_ICM20602_COMPAT_H
#define LRRK_LITEWING_PIOS_ICM20602_COMPAT_H

#include <pios_sensors.h>

extern const PIOS_SENSORS_Driver PIOS_ICM20602_Driver;

#endif /* LRRK_LITEWING_PIOS_ICM20602_COMPAT_H */
