cmake_minimum_required(VERSION 3.14...3.24)

project(devilutionx-gamelist LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/CMake")
add_subdirectory(3rdParty/libzt)
add_subdirectory(3rdParty/nlohmann_json)

list(APPEND python_SRCS
  bot_db.py
  discord_bot.py
  ztapi_client.py)

add_executable(devilutionx-gamelist
  main.cpp
)

if(NOT ANDROID)
  target_link_libraries(devilutionx-gamelist PUBLIC zt-static)
else()
  target_link_libraries(devilutionx-gamelist PUBLIC zt-shared)
endif()

target_link_libraries(devilutionx-gamelist PRIVATE nlohmann_json::nlohmann_json)

foreach(src ${python_SRCS})
  file(CREATE_LINK "${CMAKE_CURRENT_SOURCE_DIR}/${src}" "${CMAKE_CURRENT_BINARY_DIR}/${src}" SYMBOLIC)
endforeach()

install(TARGETS devilutionx-gamelist
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR})
