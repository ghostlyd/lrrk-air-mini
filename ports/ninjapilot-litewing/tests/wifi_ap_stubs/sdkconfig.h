/* Host fixture only, not a firmware configuration. IDF 5.3.2's
 * esp_wifi_types_generic.h uses these four selectors for NAN/HE type branches.
 * Select ESP32-S3 Wi-Fi types without a generated target build directory. */
#pragma once
#define CONFIG_SOC_WIFI_ENABLED 1
#define CONFIG_SOC_WIFI_SUPPORTED 1
#define CONFIG_SOC_WIFI_NAN_SUPPORT 0
#define CONFIG_SOC_WIFI_HE_SUPPORT 0
