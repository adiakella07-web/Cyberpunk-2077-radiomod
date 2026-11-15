// Neon Dial launcher: a tiny RED4ext plugin that starts NeonDial.exe (sitting next to this DLL)
// when the game loads (it stops itself when the game exits). So launching the game from Vortex is enough.
// Only the plugin-API headers are needed (we are a loader, we don't touch game internals).
#include <RED4ext/Common.hpp>
#include <RED4ext/Api/ApiVersion.hpp>
#include <RED4ext/Api/v1/EMainReason.hpp>
#include <RED4ext/Api/v1/PluginHandle.hpp>
#include <RED4ext/Api/v1/PluginInfo.hpp>
#include <RED4ext/Api/v1/Runtime.hpp>
#include <RED4ext/Api/v1/Sdk.hpp>
#include <RED4ext/Api/v1/Version.hpp>

#include <string>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

namespace
{
PROCESS_INFORMATION g_proc{};

std::wstring ThisDllDir()
{
    HMODULE module = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       reinterpret_cast<LPCWSTR>(&ThisDllDir), &module);
    wchar_t path[MAX_PATH]{};
    GetModuleFileNameW(module, path, MAX_PATH);
    std::wstring p(path);
    return p.substr(0, p.find_last_of(L"\\/"));
}

void StartCompanion()
{
    const std::wstring dir = ThisDllDir();
    std::wstring cmd = L"\"" + dir + L"\\NeonDial.exe\" --watch-pid " + std::to_wstring(GetCurrentProcessId());
    STARTUPINFOW si{};
    si.cb = sizeof(si);
    // If a copy is already running the new one exits by itself (port already in use).
    CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, dir.c_str(), &si, &g_proc);
}

void StopCompanion()
{
    // NeonDial.exe watches the game's process id and shuts down cleanly by itself (it must restore the
    // music app's volume first), so we deliberately don't kill it here.
    if (g_proc.hProcess)
    {
        CloseHandle(g_proc.hProcess);
        CloseHandle(g_proc.hThread);
        g_proc = {};
    }
}
} // namespace

RED4EXT_C_EXPORT bool RED4EXT_CALL Main(RED4ext::v1::PluginHandle aHandle, RED4ext::v1::EMainReason aReason,
                                        const RED4ext::v1::Sdk* aSdk)
{
    RED4EXT_UNUSED_PARAMETER(aHandle);
    RED4EXT_UNUSED_PARAMETER(aSdk);

    switch (aReason)
    {
    case RED4ext::v1::EMainReason::Load:
        StartCompanion();
        break;
    case RED4ext::v1::EMainReason::Unload:
        StopCompanion();
        break;
    }
    return true;
}

RED4EXT_C_EXPORT void RED4EXT_CALL Query(RED4ext::v1::PluginInfo* aInfo)
{
    aInfo->name = L"NeonDial";
    aInfo->author = L"NeonDial";
    aInfo->version = RED4EXT_V1_SEMVER(1, 0, 0);
    aInfo->runtime = RED4EXT_V1_RUNTIME_VERSION_INDEPENDENT; // loader only, doesn't touch game internals
    aInfo->sdk = RED4EXT_V1_SDK_VERSION_CURRENT;
}

RED4EXT_C_EXPORT uint32_t RED4EXT_CALL Supports()
{
    return RED4EXT_API_VERSION_1;
}
