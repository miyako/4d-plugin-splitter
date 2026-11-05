cmake_minimum_required(VERSION 3.24)
if(CMAKE_HOST_APPLE AND NOT DEFINED CMAKE_OSX_DEPLOYMENT_TARGET)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "12.0" CACHE STRING "Minimum macOS deployment target")
endif()
project(Splitter VERSION 0.1.0 LANGUAGES CXX)

if(NOT APPLE AND NOT WIN32)
    message(FATAL_ERROR "The native 4D plug-in targets macOS and Windows only")
endif()
if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "Only 64-bit hosts are supported")
endif()
if(WIN32 AND NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(AMD64|amd64|x86_64)$")
    message(FATAL_ERROR "The Windows target is x64, not ARM64")
endif()
if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    add_compile_options(/utf-8)
endif()
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/dependencies.lock.json")
configure_file(cmake/build-toolchain.json.in build-toolchain.json @ONLY)

include(FetchContent)
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/dependencies.lock.json" dependency_lock)
string(JSON sdk_url GET "${dependency_lock}" sdk url)
string(JSON sdk_sha256 GET "${dependency_lock}" sdk sha256)
FetchContent_Declare(fourd_sdk URL "${sdk_url}" URL_HASH "SHA256=${sdk_sha256}")
FetchContent_MakeAvailable(fourd_sdk)
set(sdk_dir "${fourd_sdk_SOURCE_DIR}/4D Plugin API")
set_source_files_properties("${sdk_dir}/4DPluginAPI.c" PROPERTIES LANGUAGE CXX)
include(cmake/ICU.cmake)
include(CTest)
find_package(Threads REQUIRED)

add_library(splitter_core STATIC src/core/split.cpp src/core/icu_runtime.cpp)
file(SIZE "${SPLITTER_ICU_DATA}" splitter_data_size)
target_compile_definitions(splitter_core PRIVATE SPLITTER_ICU_DATA_SIZE=${splitter_data_size})
target_compile_features(splitter_core PUBLIC cxx_std_17)
target_include_directories(splitter_core PUBLIC src/core)
target_link_libraries(splitter_core PUBLIC splitter_icu_i18n Threads::Threads)
set_target_properties(splitter_core PROPERTIES POSITION_INDEPENDENT_CODE TRUE
    CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN TRUE)

function(splitter_bundle target source manifest output_directory)
    add_library(${target} MODULE "${source}" "${sdk_dir}/4DPluginAPI.c")
    target_compile_features(${target} PRIVATE cxx_std_17)
    target_include_directories(${target} PRIVATE "${sdk_dir}")
    target_compile_definitions(${target} PRIVATE UNICODE _UNICODE NOMINMAX WIN32_LEAN_AND_MEAN)
    set_target_properties(${target} PROPERTIES PREFIX "" OUTPUT_NAME Splitter
        CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN TRUE)
    if(APPLE)
        set_target_properties(${target} PROPERTIES BUNDLE TRUE BUNDLE_EXTENSION bundle
            LIBRARY_OUTPUT_DIRECTORY "${output_directory}")
        target_link_libraries(${target} PRIVATE "-framework CoreGraphics")
        target_link_options(${target} PRIVATE "-Wl,-exported_symbol,_FourDPackex")
        set(contents "$<TARGET_BUNDLE_DIR:${target}>/Contents")
    else()
        set(contents "${output_directory}/Splitter.bundle/Contents")
        set_target_properties(${target} PROPERTIES SUFFIX ".4DX"
            LIBRARY_OUTPUT_DIRECTORY "${contents}/Windows64"
            RUNTIME_OUTPUT_DIRECTORY "${contents}/Windows64")
        foreach(config DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
            set_target_properties(${target} PROPERTIES
                RUNTIME_OUTPUT_DIRECTORY_${config} "${contents}/Windows64")
        endforeach()
        target_sources(${target} PRIVATE "${sdk_dir}/4DPluginAPI.def")
        target_link_libraries(${target} PRIVATE user32 gdi32)
    endif()
    add_custom_command(TARGET ${target} POST_BUILD
        COMMAND "${CMAKE_COMMAND}" -E make_directory "${contents}/Resources/licenses"
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/cmake/Info.plist" "${contents}/Info.plist"
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${manifest}"
            "${contents}/Resources/manifest.json"
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/licenses/4D-Plugin-SDK.txt"
            "${contents}/Resources/licenses/4D-Plugin-SDK.txt"
    )
endfunction()

splitter_bundle(Splitter src/plugin/splitter.cpp
    "${CMAKE_CURRENT_SOURCE_DIR}/resources/manifest.json" "${CMAKE_BINARY_DIR}/plugins")
target_link_libraries(Splitter PRIVATE splitter_core)
if(APPLE)
    set(product_contents "$<TARGET_BUNDLE_DIR:Splitter>/Contents")
else()
    set(product_contents "${CMAKE_BINARY_DIR}/plugins/Splitter.bundle/Contents")
endif()
add_custom_command(TARGET Splitter POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${SPLITTER_ICU_DATA}"
        "${product_contents}/Resources/icudt79l.dat"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${splitter_icu_SOURCE_DIR}/LICENSE"
        "${product_contents}/Resources/licenses/ICU-LICENSE.txt"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
        "${CMAKE_CURRENT_SOURCE_DIR}/dependencies.lock.json"
        "${product_contents}/Resources/dependencies.lock.json"
)

option(SPLITTER_BUILD_PROBES "Build historical Gate 0 diagnostic commands" OFF)
if(SPLITTER_BUILD_PROBES)
    splitter_bundle(SplitterProbe src/plugin/probe.cpp
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/probes/manifest.json" "${CMAKE_BINARY_DIR}/probes")
endif()
if(BUILD_TESTING)
    add_executable(splitter_native_tests tests/native/split_tests.cpp)
    target_link_libraries(splitter_native_tests PRIVATE splitter_core)
    add_test(NAME splitter_native COMMAND splitter_native_tests "${SPLITTER_ICU_DATA}")
endif()
