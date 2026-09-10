# Task stacks contain pilot credentials. Check effective IDF configuration,
# not only defaults: an existing sdkconfig can retain unsafe dump settings.
if(NOT CONFIG_ESP_COREDUMP_ENABLE_TO_NONE OR
   CONFIG_ESP_COREDUMP_ENABLE_TO_FLASH OR
   CONFIG_ESP_COREDUMP_ENABLE_TO_UART)
    message(FATAL_ERROR "Pilot credentials require core dumps disabled; select CONFIG_ESP_COREDUMP_ENABLE_TO_NONE and reconfigure")
endif()
