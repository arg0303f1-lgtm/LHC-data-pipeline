cmake_minimum_required(VERSION 3.14)
project(lhc_event_generator
    VERSION 1.0.0
    DESCRIPTION "Simulated LHC collision event generator"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ── Dependencies ──────────────────────────────────────────────
include(FetchContent)
FetchContent_Declare(
    json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG        v3.11.3
    GIT_SHALLOW    TRUE
)
FetchContent_MakeAvailable(json)

# ── Event Generator Library ──────────────────────────────────
add_library(event_generator_lib
    src/event_generator.cpp
)
target_include_directories(event_generator_lib PUBLIC include)
target_link_libraries(event_generator_lib PUBLIC nlohmann_json::nlohmann_json)
target_compile_options(event_generator_lib PRIVATE -Wall -Wextra -O2)

# ── Main Executable ──────────────────────────────────────────
add_executable(event_generator src/main.cpp)
target_link_libraries(event_generator PRIVATE event_generator_lib)
target_compile_options(event_generator PRIVATE -Wall -Wextra -O2)

# ── Install ──────────────────────────────────────────────────
install(TARGETS event_generator RUNTIME DESTINATION bin)

# ── Summary ──────────────────────────────────────────────────
message(STATUS "")
message(STATUS "  LHC Event Generator v${PROJECT_VERSION}")
message(STATUS "  C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "  Build Type:   ${CMAKE_BUILD_TYPE}")
message(STATUS "")
