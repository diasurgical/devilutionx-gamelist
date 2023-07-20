cmake_minimum_required(VERSION 3.14)

set(CMAKE_POLICY_DEFAULT_CMP0077 NEW)

project(devilutionx-gamelist LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/CMake")
add_subdirectory(3rdParty/libzt)
add_subdirectory(3rdParty/nlohmann_json)

add_executable(devilutionx-gamelist
  main.cpp
)

if(NOT ANDROID)
  target_link_libraries(devilutionx-gamelist PUBLIC zt-static)
else()
  target_link_libraries(devilutionx-gamelist PUBLIC zt-shared)
endif()

target_link_libraries(devilutionx-gamelist PRIVATE nlohmann_json::nlohmann_json)

install(TARGETS devilutionx-gamelist
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR})
