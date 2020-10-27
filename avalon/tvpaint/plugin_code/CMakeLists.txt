cmake_minimum_required(VERSION 3.17)
project(AvalonPlugin C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
set(IP_ENABLE_UNICODE OFF)
set(IP_ENABLE_DOCTEST OFF)

if(MSVC)
    add_definitions(-D_CRT_SECURE_NO_WARNINGS)
endif()

# get from environemnts
set(BOOST_ROOT "C:/libs/boost/x86")

set(OPENSSL_INCLUDE "C:/libs/openssl/build/x86/Debug/static/include")
set(OPENSSL_LIB_DIR "C:/libs/openssl/build/x86/Debug/static/lib")

set(WEBSOCKETPP_INCLUDE "C:/libs/websocketpp/include")
set(WEBSOCKETPP_LIB_DIR "C:/libs/websocketpp/Debug/x86")

set(JSONRPCPP_SOURCE_DIR "C:/libs/jsonrpcpp/source")
set(JSONRPCPP_INCLUDE "${JSONRPCPP_SOURCE_DIR}/include")

set(PTHREAD_INCLUDE "C:/libs/pthread/x86/include")
set(PTHREAD_LIB_DIR "C:/libs/pthread/x86/Debug/static")

include_directories(
        "${TVPAINT_SDK_INCLUDE}"
        "${OPENSSL_INCLUDE}"
        "${WEBSOCKETPP_INCLUDE}"
        "${JSONRPCPP_INCLUDE}"
        "${PTHREAD_INCLUDE}"
)
link_directories(
        "${OPENSSL_LIB_DIR}"
        "${WEBSOCKETPP_LIB_DIR}"
        "${PTHREAD_LIB_DIR}"
)
add_library(jsonrpcpp INTERFACE)
find_package(Boost 1.72.0 COMPONENTS random)

find_library(pthreadVSE3d NAMES pthreadVSE3d)
find_library(pthreadVCE3d NAMES pthreadVCE3d)
find_library(pthreadVC3d NAMES pthreadVC3d)

add_library(${PROJECT_NAME} SHARED library.cpp library.def "${TVPAINT_SDK_LIB}/dllx.c")

include_directories(${Boost_INCLUDE_DIR})
target_link_libraries(${PROJECT_NAME} ${Boost_LIBRARIES})
target_link_libraries(${PROJECT_NAME} jsonrpcpp)
target_link_libraries(${PROJECT_NAME} pthreadVSE3d)
target_link_libraries(${PROJECT_NAME} pthreadVCE3d)
target_link_libraries(${PROJECT_NAME} pthreadVC3d)
