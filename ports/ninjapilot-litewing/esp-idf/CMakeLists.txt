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
