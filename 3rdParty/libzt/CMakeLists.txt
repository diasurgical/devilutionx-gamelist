include(functions/FetchContent_MakeAvailableExcludeFromAll)

set(BUILD_HOST_SELFTEST OFF)
set(LWIP_FLAGS "-DLWIP_IPV6_FORWARD=1")

include(FetchContent)
if (CMAKE_VERSION VERSION_GREATER_EQUAL "3.28.0")
  FetchContent_Declare(libzt
    GIT_REPOSITORY https://github.com/diasurgical/libzt.git
    GIT_TAG 72a518bcf7d87e32f718ca612ce2c8303ceedd12
    EXCLUDE_FROM_ALL)
  FetchContent_MakeAvailable(libzt)
else()
  FetchContent_Declare(libzt
    GIT_REPOSITORY https://github.com/diasurgical/libzt.git
    GIT_TAG 72a518bcf7d87e32f718ca612ce2c8303ceedd12)
  FetchContent_MakeAvailableExcludeFromAll(libzt)
endif()

if(NOT ANDROID)
  set(libzt_LIB_NAME zt-static)
else()
  set(libzt_LIB_NAME zt-shared)
endif()

foreach(
  lib_name
  zto_obj
  libnatpmp_obj
  libzt_obj
  lwip_obj
  miniupnpc_obj
  zto_pic
  natpmp_pic
  lwip_pic
  miniupnpc_pic
  ztcore
  ${libzt_LIB_NAME}
)
  if(TARGET ${lib_name})
    # External library, ignore all warnings
    target_compile_options(${lib_name} PRIVATE -w)
  endif()
endforeach(lib_name)

target_include_directories(${libzt_LIB_NAME} INTERFACE
  "${libzt_SOURCE_DIR}/include"
  "${libzt_SOURCE_DIR}/src"
  "${libzt_SOURCE_DIR}/ext/lwip/src/include")

if(WIN32)
  target_include_directories(${libzt_LIB_NAME} INTERFACE
    "${libzt_SOURCE_DIR}/ext/lwip-contrib/ports/win32/include")
else()
  target_include_directories(${libzt_LIB_NAME} INTERFACE
    "${libzt_SOURCE_DIR}/ext/lwip-contrib/ports/unix/port/include")
endif()

if(MINGW_CROSS)
  include(zt_defs REQUIRED)
endif()

if(MSVC)
  target_compile_definitions(libnatpmp_obj PRIVATE -DSTATICLIB)
endif()
