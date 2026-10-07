# VitaPort.cmake: the Vita target and the PC "Vita simulation" profile for a CMake project.
# Shipped by ps-vita-porter (`vita init --kit` copies it to cmake/VitaPort.cmake; MIT). Yours to edit.
#
#   include(cmake/VitaPort.cmake)
#   if(VITA)                                  # set by $VITASDK/share/vita.toolchain.cmake
#     vitaport_link_vita(game)                # kit sources + Sce stubs
#     target_link_libraries(game PRIVATE ${VITAPORT_VITAGL_LIBS})   # if the game renders through vitaGL
#     vitaport_package(game)                  # eboot.bin + .vpk with sce_sys/ and (embedded mode) the assets
#   elseif(VITA_SIM)
#     vitaport_link_sim(game)                 # PC: Vita controls, paths, memory cap, scripted input, screenshots
#   endif()
#
# `vita build` passes the values below from vita.toml; the defaults let a plain CMake configure work too.

if(VITA)
  include("${VITASDK}/share/vita.cmake" REQUIRED)   # vita_create_self, vita_create_vpk
endif()

set(VITAPORT_KIT_DIR "${CMAKE_CURRENT_LIST_DIR}/../platform/vita/vitaport" CACHE PATH "Folder with vitaport.h and its sources")
option(VITA_SIM "PC build: the Vita simulation profile (960x544, Vita controls, memory cap)" OFF)

set(VITA_TITLEID "VPRT00001" CACHE STRING "Title ID: 4 uppercase letters + 5 digits")
set(VITA_APP_NAME "${PROJECT_NAME}" CACHE STRING "Name under the LiveArea bubble")
set(VITA_VERSION "01.00" CACHE STRING "APP_VER, ##.##")
set(VITA_DATA_FOLDER "${PROJECT_NAME}" CACHE STRING "ux0:data/<folder>/ for saves, logs and external assets")
set(VITA_ASSETS_MODE "embedded" CACHE STRING "embedded (app0:) or external (ux0:data/<folder>/)")
set_property(CACHE VITA_ASSETS_MODE PROPERTY STRINGS embedded external)
set(VITA_ASSETS_DIR "${CMAKE_SOURCE_DIR}/build-vita/assets" CACHE PATH "Converted assets (vita assets convert)")
set(VITA_ASSETS_VPK_DIR "assets" CACHE STRING "Folder name of the game data inside the .vpk / ux0:data/<folder>/")
set(VITA_LIVEAREA_DIR "${CMAKE_SOURCE_DIR}/sce_sys" CACHE PATH "sce_sys/ (vita livearea make)")
option(VITA_UNSAFE "Unsafe eboot (needs a reason in PORT_PLAN.md)" OFF)
option(VITA_EXTENDED_MEMORY "ATTRIBUTE2=12: 365 MiB of main memory instead of 256 (reinstall needed)" OFF)
set(VITA_LOG_HOST "" CACHE STRING "PC IP for the UDP network log (vita logs); empty = off")
set(VITA_LOG_PORT "18194" CACHE STRING "UDP port of the network log")

# What a vitaGL renderer links on the Vita (order matters for static libraries).
set(VITAPORT_VITAGL_LIBS vitaGL vitashark SceShaccCgExt mathneon taihen_stub SceShaccCg_stub SceKernelDmacMgr_stub SceGxm_stub
    SceDisplay_stub SceAppMgr_stub SceCommonDialog_stub SceIme_stub SceSysmodule_stub SceLibKernel_stub m)

function(vitaport__defines target)
  if(VITA_ASSETS_MODE STREQUAL "external")
    set(ext 1)
  else()
    set(ext 0)
  endif()
  target_compile_definitions(${target} PRIVATE VP_DATA_FOLDER="${VITA_DATA_FOLDER}" VP_ASSETS_DIR="${VITA_ASSETS_VPK_DIR}"
                             VP_ASSETS_EXTERNAL=${ext})
  target_include_directories(${target} PRIVATE "${VITAPORT_KIT_DIR}")
endfunction()

function(vitaport_link_vita target)
  vitaport__defines(${target})
  target_sources(${target} PRIVATE "${VITAPORT_KIT_DIR}/vitaport_vita.c")
  target_link_libraries(${target} PRIVATE SceCtrl_stub SceTouch_stub SceMotion_stub SceAppUtil_stub SceSysmodule_stub)
  if(VITA_LOG_HOST)
    target_compile_definitions(${target} PRIVATE VP_LOG_HOST="${VITA_LOG_HOST}" VP_LOG_PORT=${VITA_LOG_PORT})
    target_link_libraries(${target} PRIVATE SceNet_stub SceNetCtl_stub)
  endif()
endfunction()

function(vitaport_link_sim target)
  vitaport__defines(${target})
  target_compile_definitions(${target} PRIVATE VITA_SIM=1)
  target_sources(${target} PRIVATE "${VITAPORT_KIT_DIR}/vitaport_sim.c" "${VITAPORT_KIT_DIR}/vitaport_alloc.cpp")
  if(TARGET SDL3::SDL3)
    target_compile_definitions(${target} PRIVATE VP_SDL3=1)
  endif()
  # count malloc/calloc/realloc/free too where the linker can wrap them (GNU ld / lld; not MSVC or Apple ld64)
  if(NOT MSVC AND NOT APPLE AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_definitions(${target} PRIVATE VP_WRAP_MALLOC=1)
    target_link_options(${target} PRIVATE "LINKER:--wrap=malloc,--wrap=calloc,--wrap=realloc,--wrap=free")
  endif()
endfunction()

function(vitaport_package target)
  if(VITA_UNSAFE)
    vita_create_self(eboot.bin ${target} UNSAFE)
  else()
    vita_create_self(eboot.bin ${target})
  endif()
  set(files)
  if(EXISTS "${VITA_LIVEAREA_DIR}")
    list(APPEND files FILE "${VITA_LIVEAREA_DIR}" sce_sys)
  else()
    message(WARNING "no LiveArea folder at ${VITA_LIVEAREA_DIR}: run `vita livearea make` (the .vpk will lack icon0/pic0/bg0/startup)")
  endif()
  if(VITA_ASSETS_MODE STREQUAL "embedded")
    if(EXISTS "${VITA_ASSETS_DIR}")
      list(APPEND files FILE "${VITA_ASSETS_DIR}" "${VITA_ASSETS_VPK_DIR}")
    else()
      message(WARNING "embedded assets requested but ${VITA_ASSETS_DIR} doesn't exist: run `vita assets convert` first")
    endif()
  endif()
  if(VITA_EXTENDED_MEMORY)
    set(VITA_MKSFOEX_FLAGS "${VITA_MKSFOEX_FLAGS} -d ATTRIBUTE2=12")
  endif()
  vita_create_vpk(${target}.vpk ${VITA_TITLEID} eboot.bin VERSION ${VITA_VERSION} NAME "${VITA_APP_NAME}" ${files})
endfunction()
