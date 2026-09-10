# Repository-owned target adapter sources for the NinjaPilot ESP-IDF wrapper.
#
# The wrapper must also provide the pinned reference ESP32 PiOS backend
# (pios_esp32.h, pios_esp32_priv.h, pios_i2c.c, and the common ESP32 support
# files). This fragment intentionally lists only the LiteWing replacements:
# the reference servo and ICM-20602 sources must not be linked for this target.

set(LITEWING_TARGET_SRCS
    ${CMAKE_CURRENT_LIST_DIR}/../contract/litewing_contract.c
    ${CMAKE_CURRENT_LIST_DIR}/litewing_mpu6050_protocol.c
    ${CMAKE_CURRENT_LIST_DIR}/litewing_boot_readiness.c
    ${CMAKE_CURRENT_LIST_DIR}/pios_litewing_mpu6050.c
    ${CMAKE_CURRENT_LIST_DIR}/pios_litewing_brushed_pwm.c
    ${CMAKE_CURRENT_LIST_DIR}/pios_litewing_board.c
    ${CMAKE_CURRENT_LIST_DIR}/pios_litewing_flashfs_nvs.c
    ${CMAKE_CURRENT_LIST_DIR}/litewing_settings_recovery.c
    ${CMAKE_CURRENT_LIST_DIR}/litewing_uavobject_delete.c
    ${CMAKE_CURRENT_LIST_DIR}/pios_litewing_gcsrcvr.c
    ${CMAKE_CURRENT_LIST_DIR}/litewing_battery_voltage.c
    ${CMAKE_CURRENT_LIST_DIR}/pios_litewing_battery.c
    ${CMAKE_CURRENT_LIST_DIR}/litewing_battery_module.c
)

set(LITEWING_TARGET_INCLUDE_DIRS
    ${CMAKE_CURRENT_LIST_DIR}/include
    ${CMAKE_CURRENT_LIST_DIR}/../contract
)
