# No-flash ESP-IDF project for the repository-owned LiteWing target wrapper.
#
# The flight tree and the ESP32 PiOS backend remain pinned external inputs;
# this project only composes them with the LiteWing board adapter. The build
# refuses to configure without those exact checkouts and never defines a
# flash target of its own.
cmake_minimum_required(VERSION 3.16)

if(NOT DEFINED ENV{IDF_PATH})
    message(FATAL_ERROR "IDF_PATH is not set; source the pinned ESP-IDF environment first")
endif()

set(EXTRA_COMPONENT_DIRS)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(lrrk_litewing_ninjapilot)

# Inspect the linked artifact on every build, including no-op rebuilds.
# This catches accidental removal of the persistence archive anchor; it is
# not a settings-durability or hardware-readiness claim.
idf_build_get_property(litewing_python PYTHON)
add_custom_target(litewing_persistence_gate ALL
    COMMAND "${litewing_python}" "${CMAKE_CURRENT_LIST_DIR}/../verify_persistence_link.py"
            --elf "$<TARGET_FILE:${CMAKE_PROJECT_NAME}.elf>" --nm "${CMAKE_NM}"
    DEPENDS ${CMAKE_PROJECT_NAME}.elf
    VERBATIM)

# Direct application/flash targets must accept the ELF through the same gate,
# not merely rely on ALL. No flash command is executed by this dependency.
add_dependencies(gen_project_binary litewing_persistence_gate)
add_dependencies(app litewing_persistence_gate)
foreach(litewing_flash_target IN ITEMS flash app-flash)
    if(TARGET ${litewing_flash_target})
        add_dependencies(${litewing_flash_target} litewing_persistence_gate)
    endif()
endforeach()
