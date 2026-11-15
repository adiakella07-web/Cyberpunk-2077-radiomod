cmake_minimum_required(VERSION 3.21)
project(NeonDial_launcher LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# CI clones https://github.com/WopsS/RED4ext.SDK into ./RED4ext.SDK; only its headers are used.
add_library(NeonDial SHARED Main.cpp)
target_include_directories(NeonDial PRIVATE RED4ext.SDK/include)
target_compile_definitions(NeonDial PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
