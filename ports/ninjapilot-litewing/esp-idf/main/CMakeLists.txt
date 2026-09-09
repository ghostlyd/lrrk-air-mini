# ESP-IDF main component for the LiteWing target.
#
# The source boundary is intentionally explicit. Generated UAVObjects and the
# two pinned upstream trees are checked before CMake registers the component;
# a partial or wrong checkout must not produce a firmware artifact that looks
# trustworthy.
set(PORT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../..")
get_filename_component(PORT_ROOT "${PORT_ROOT}" ABSOLUTE)

if(DEFINED IDF_TARGET AND NOT "${IDF_TARGET}" STREQUAL "esp32s3")
    message(FATAL_ERROR "LiteWing target wrapper requires IDF_TARGET=esp32s3")
endif()

if(NOT DEFINED NINJAPILOT_ROOT AND DEFINED ENV{NINJAPILOT_ROOT})
    # ESP-IDF evaluates component requirements in a separate CMake process.
    # Cache variables passed to the top-level configure are not guaranteed to
    # be present there, so the build wrapper exports the same paths as an
    # environment-backed fallback.
    set(NINJAPILOT_ROOT "$ENV{NINJAPILOT_ROOT}")
endif()
if(NOT DEFINED OPENPILOT_ESP32_ROOT AND DEFINED ENV{OPENPILOT_ESP32_ROOT})
    set(OPENPILOT_ESP32_ROOT "$ENV{OPENPILOT_ESP32_ROOT}")
endif()

if(NOT DEFINED NINJAPILOT_ROOT)
    message(FATAL_ERROR "NINJAPILOT_ROOT is required; use the pinned NinjaPilot checkout")
endif()
if(NOT DEFINED OPENPILOT_ESP32_ROOT)
    message(FATAL_ERROR "OPENPILOT_ESP32_ROOT is required; use the pinned ESP32 backend checkout")
endif()
get_filename_component(NINJAPILOT_ROOT "${NINJAPILOT_ROOT}" ABSOLUTE)
get_filename_component(OPENPILOT_ESP32_ROOT "${OPENPILOT_ESP32_ROOT}" ABSOLUTE)

execute_process(
    COMMAND python3 "${PORT_ROOT}/verify_external_sources.py"
            --manifest "${PORT_ROOT}/SOURCE_MANIFEST.json"
            --flight "${NINJAPILOT_ROOT}"
            --reference "${OPENPILOT_ESP32_ROOT}"
    RESULT_VARIABLE SOURCE_VERIFY_RC
    OUTPUT_VARIABLE SOURCE_VERIFY_OUT
    ERROR_VARIABLE SOURCE_VERIFY_ERR)
if(NOT SOURCE_VERIFY_RC EQUAL 0)
    message(FATAL_ERROR
        "Pinned external source verification failed.\n"
        "${SOURCE_VERIFY_OUT}\n${SOURCE_VERIFY_ERR}")
endif()

set(FLIGHT "${NINJAPILOT_ROOT}/flight")
set(ESP32PORT "${OPENPILOT_ESP32_ROOT}")
set(TARGET_ROOT "${PORT_ROOT}/target")
set(BOARD_ROOT "${TARGET_ROOT}/firmware")
set(UAVOSYNTH "${NINJAPILOT_ROOT}/build/uavobject-synthetics/flight")

if(NOT EXISTS "${UAVOSYNTH}/uavobjectsinit.c")
    message(FATAL_ERROR
        "Generated flight UAVObjects are missing at ${UAVOSYNTH}.\n"
        "Run 'make uavobjects_flight' in the pinned NinjaPilot checkout "
        "before configuring this ESP-IDF project.")
endif()

# Repository-owned adapter fragment. It must not pull in the reference
# servo-pulse or ICM-20602 implementations for LiteWing.
include("${TARGET_ROOT}/sources.cmake")

# --- PiOS: pinned ESP32 backend ---------------------------------------
set(PIOS_ESP32_SRCS
    "${ESP32PORT}/pios/esp32/pios_sys.c"
    "${ESP32PORT}/pios/esp32/pios_delay.c"
    "${ESP32PORT}/pios/esp32/pios_irq.c"
    "${ESP32PORT}/pios/esp32/pios_led.c"
    "${ESP32PORT}/pios/esp32/pios_debug.c"
    "${ESP32PORT}/pios/esp32/pios_wdg.c"
    "${ESP32PORT}/pios/esp32/pios_usart.c"
    "${ESP32PORT}/pios/esp32/pios_i2c.c"
    "${ESP32PORT}/pios/esp32/pios_task_runtime.c"
)

# --- PiOS: shared flight services ------------------------------------
# The architecture-specific LED implementation replaces the STM32 GPIO LED
# source. The reference servo and ICM-20602 files are deliberately absent.
set(PIOS_COMMON_SRCS
    "${FLIGHT}/pios/common/pios_com.c"
    "${FLIGHT}/pios/common/pios_rcvr.c"
    "${FLIGHT}/pios/common/pios_gcsrcvr.c"
    "${FLIGHT}/pios/common/pios_mem.c"
    "${FLIGHT}/pios/common/pios_crc.c"
    "${FLIGHT}/pios/common/pios_deltatime.c"
    "${FLIGHT}/pios/common/pios_sensors.c"
    "${FLIGHT}/pios/common/pios_task_monitor.c"
    "${FLIGHT}/pios/common/pios_callbackscheduler.c"
    "${FLIGHT}/pios/common/pios_notify.c"
    "${FLIGHT}/pios/common/pios_debuglog.c"
)

# --- UAVObject / UAVTalk machinery -----------------------------------
set(UAVO_CORE_SRCS
    "${FLIGHT}/uavobjects/uavobjectmanager.c"
    "${FLIGHT}/uavobjects/uavobjectpersistence.c"
    "${FLIGHT}/uavobjects/eventdispatcher.c"
    "${FLIGHT}/uavtalk/uavtalk.c"
)

# --- Flight libraries -------------------------------------------------
set(LIB_SRCS
    "${FLIGHT}/libraries/alarms.c"
    "${FLIGHT}/libraries/CoordinateConversions.c"
    "${FLIGHT}/libraries/sanitycheck.c"
    "${FLIGHT}/libraries/notification.c"
    "${FLIGHT}/libraries/optypes.c"
    "${FLIGHT}/libraries/fifo_buffer.c"
    "${FLIGHT}/libraries/math/pid.c"
    "${FLIGHT}/libraries/math/mathmisc.c"
    "${FLIGHT}/libraries/math/sin_lookup.c"
    "${FLIGHT}/libraries/math/butterworth.c"
)

# Rate-mode first bring-up: Attitude is the standalone complementary filter;
# navigation, Remote ID, Wi-Fi, and autonomous modules are intentionally not
# compiled into this first hardware target.
set(NINJA_MODULE_SRCS
    "${FLIGHT}/modules/Attitude/attitude.c"
    "${FLIGHT}/modules/Stabilization/stabilization.c"
    "${FLIGHT}/modules/Stabilization/innerloop.c"
    "${FLIGHT}/modules/Stabilization/outerloop.c"
    "${FLIGHT}/modules/Stabilization/cruisecontrol.c"
    "${FLIGHT}/modules/Stabilization/virtualflybar.c"
    "${FLIGHT}/modules/Stabilization/relay_tuning.c"
    "${FLIGHT}/modules/Actuator/actuator.c"
    "${FLIGHT}/modules/Receiver/receiver.c"
    "${FLIGHT}/modules/ManualControl/manualcontrol.c"
    "${FLIGHT}/modules/ManualControl/armhandler.c"
    "${FLIGHT}/modules/ManualControl/manualhandler.c"
    "${FLIGHT}/modules/ManualControl/stabilizedhandler.c"
    "${FLIGHT}/modules/ManualControl/pathfollowerhandler.c"
    "${FLIGHT}/modules/ManualControl/pathplannerhandler.c"
    "${FLIGHT}/modules/ManualControl/takeofflocationhandler.c"
    "${FLIGHT}/modules/Telemetry/telemetry.c"
    "${FLIGHT}/modules/System/systemmod.c"
)

set(BOARD_SRCS
    "${BOARD_ROOT}/litewing.c"
    "${BOARD_ROOT}/pios_board.c"
    "${BOARD_ROOT}/InitMods.c"
)

# Match the selected simlitewing UAVObjects.inc rather than silently compiling
# a smaller object set. The generated directory is a build prerequisite and
# remains outside this repository, while this list is reviewable and stable.
set(UAVO_NAMES
    statusgrounddrive pidstatus statusvtolland vtolselftuningstats
    accessorydesired actuatorcommand actuatordesired actuatorsettings
    attitudesettings attitudestate attitudesimulated gyrostate gyrosensor
    accelstate accelsensor accelgyrosettings ak8975sensor i2cbusscan
    missionprogress missionrecoverysettings sensorhubsettings settingsgeneration
    flipstatus remoteidsettings remoteidstatus magsensor auxmagsensor
    auxmagsettings magstate barosensor airspeedsensor airspeedsettings
    airspeedstate debuglogsettings debuglogcontrol debuglogstatus debuglogentry
    firmwareiapobj flightbatterystate flighttelemetrystats gcstelemetrystats
    gcsreceiver gpspositionsensor gpssatellites gpstime gpsvelocitysensor
    gpsextendedstatus gpssettings vtolpathfollowersettings
    groundpathfollowersettings fixedwingpathfollowersettings
    fixedwingpathfollowerstatus homelocation i2cstats manualcontrolcommand
    manualcontrolsettings flightmodesettings mixersettings mixerstatus
    objectpersistence oplinkstatus pathaction pathdesired pathplan pathstatus
    pathsummary positionstate ratedesired relaytuning relaytuningsettings
    revocalibration revosettings stabilizationdesired stabilizationsettings
    stabilizationsettingsbank1 stabilizationsettingsbank2
    stabilizationsettingsbank3 stabilizationstatus stabilizationbank
    systemalarms systemsettings systemstats taskinfo callbackinfo velocitystate
    velocitydesired watchdogstatus waypoint waypointactive poilocation
    flightstatus hwsettings receiveractivity altitudeholdsettings
    altitudefiltersettings altitudeholdstatus ekfconfiguration ekfstatevariance
    takeofflocation uavobjectsinit
)
set(UAVO_SYNTH_SRCS)
set(UAVO_INIT_DEFS)
foreach(UAVO_NAME IN LISTS UAVO_NAMES)
    list(APPEND UAVO_SYNTH_SRCS "${UAVOSYNTH}/${UAVO_NAME}.c")
    list(APPEND UAVO_INIT_DEFS "UAVOBJ_INIT_${UAVO_NAME}=1")
endforeach()

set(ALL_PORT_SRCS
    ${BOARD_SRCS}
    ${LITEWING_TARGET_SRCS}
    ${PIOS_ESP32_SRCS}
    ${PIOS_COMMON_SRCS}
    ${UAVO_CORE_SRCS}
    ${UAVO_SYNTH_SRCS}
    ${LIB_SRCS}
    ${NINJA_MODULE_SRCS})
foreach(PORT_SOURCE IN LISTS ALL_PORT_SRCS)
    if(NOT EXISTS "${PORT_SOURCE}")
        message(FATAL_ERROR "LiteWing ESP-IDF source is missing: ${PORT_SOURCE}")
    endif()
endforeach()

execute_process(
    COMMAND python3 "${NINJAPILOT_ROOT}/make/scripts/version-info.py"
            --path "${NINJAPILOT_ROOT}"
            --uavodir "${NINJAPILOT_ROOT}/shared/uavobjectdefinition"
            --template "${CMAKE_CURRENT_LIST_DIR}/fw_version_info.tpl"
            --outfile "${CMAKE_CURRENT_BINARY_DIR}/fw_version_info.h"
            --type=0x13
            --revision=0x02
    RESULT_VARIABLE FW_VERSION_RC)
if(NOT FW_VERSION_RC EQUAL 0)
    message(FATAL_ERROR "fw_version_info.h generation failed")
endif()

idf_component_register(
    SRCS ${ALL_PORT_SRCS}
    INCLUDE_DIRS
        "${CMAKE_CURRENT_BINARY_DIR}"
        "${BOARD_ROOT}"
        "${BOARD_ROOT}/inc"
        "${TARGET_ROOT}/include"
        ${LITEWING_TARGET_INCLUDE_DIRS}
        "${FLIGHT}/pios"
        "${FLIGHT}/pios/inc"
        "${ESP32PORT}/pios/esp32"
        "${ESP32PORT}/pios/esp32/inc"
        "${FLIGHT}/uavobjects"
        "${FLIGHT}/uavobjects/inc"
        "${FLIGHT}/uavtalk"
        "${FLIGHT}/uavtalk/inc"
        "${FLIGHT}/libraries/inc"
        "${FLIGHT}/libraries/math"
        "${FLIGHT}/modules/Attitude/inc"
        "${FLIGHT}/modules/Stabilization/inc"
        "${FLIGHT}/modules/Actuator/inc"
        "${FLIGHT}/modules/ManualControl/inc"
        "${FLIGHT}/modules/Telemetry/inc"
        "${FLIGHT}/modules/System/inc"
        "${UAVOSYNTH}"
        "$ENV{IDF_PATH}/components/freertos/FreeRTOS-Kernel/include/freertos"
    REQUIRES
        driver
        esp_timer
        esp_system
        esp_hw_support
        nvs_flash
)

target_linker_script(${COMPONENT_LIB} INTERFACE "uavo_handles.ld")

# The pinned delete implementation discards erase/commit failures. Keep the
# upstream file untouched, rename only its unchecked entry point, and bind
# callers to the checked repository-owned UAVObjDelete implementation.
set_source_files_properties("${FLIGHT}/uavobjects/uavobjectpersistence.c"
    PROPERTIES COMPILE_DEFINITIONS "UAVObjDelete=UAVObjDelete_unchecked")

target_compile_definitions(${COMPONENT_LIB} PRIVATE
    USE_ESP32=1
    ESP_PLATFORM=1
    ODID_AUTH_MAX_PAGES=1
    ${UAVO_INIT_DEFS})

target_compile_options(${COMPONENT_LIB} PRIVATE
    -fsingle-precision-constant
    -Wno-unused-parameter
    -Wno-error=stringop-overread
    -Wno-error=stringop-overflow
    -Wno-error=array-bounds)
