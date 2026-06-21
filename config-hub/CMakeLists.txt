cmake_minimum_required(VERSION 3.20)
set(EXTRA_COMPONENT_DIRS main)

# Derive firmware version from git tag/commit
execute_process(
    COMMAND git describe --tags --always --dirty --match "v*"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE LOTSE_VERSION
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
)
if(LOTSE_VERSION STREQUAL "")
    set(LOTSE_VERSION "v0.0.0-dev")
endif()
add_compile_definitions(LOTSE_VERSION="${LOTSE_VERSION}")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(lotse_config_hub)
