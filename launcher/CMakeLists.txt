cmake_minimum_required(VERSION 3.21)
project(NeonDial_native LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")   # static CRT: nothing extra to install

# RED4ext plugin that starts the companion with the game.
# CI clones https://github.com/WopsS/RED4ext.SDK into ./RED4ext.SDK; only its headers are used.
add_library(NeonDial SHARED Main.cpp)
target_include_directories(NeonDial PRIVATE RED4ext.SDK/include)
target_compile_definitions(NeonDial PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Helper: captures one app's audio (process loopback) and sets per-app mixer volume.
add_executable(NeonDialAudio audio_helper.cpp)
target_compile_definitions(NeonDialAudio PRIVATE UNICODE _UNICODE NOMINMAX)
target_link_libraries(NeonDialAudio PRIVATE mmdevapi ole32 uuid)
