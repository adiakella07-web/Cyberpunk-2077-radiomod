// NeonDialAudio.exe - tiny helper for Neon Dial.
//   NeonDialAudio.exe sessions                  list audio sessions on the default output: "<pid> <state 0=inactive 1=active> <peak>"
//   NeonDialAudio.exe capture <pid> [exclude]   raw PCM (S16LE, 44.1 kHz, stereo) of that app (and its child processes)
//                                               to stdout, via Windows process loopback. Needs Windows 10 2004+.
//   NeonDialAudio.exe volume <0..1> <pid>...    set the Windows mixer volume of those apps' sessions; prints "<pid> <previous>"
//                                               (a negative value only reads the current volumes)
//   While capturing, commands can be sent on stdin, one per line:
//     gain <factor>                              multiply the captured audio
//     duck <volume> <factor> <pid>...            set those apps' volume AND the gain at the same instant, so turning an app down
//                                               while boosting the capture back is seamless (no dip, no spike)
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <initguid.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audioclientactivationparams.h>
#include <audiopolicy.h>
#include <endpointvolume.h>

#include <fcntl.h>
#include <io.h>
#include <cstdio>
#include <cstdlib>
#include <algorithm>
#include <atomic>
#include <cwchar>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace
{
int SetVolume(float volume, const std::set<DWORD>& pids, bool print);

std::atomic<float> g_gain{1.0f};

// Reads commands from stdin (see the header comment). Runs for as long as the capture runs.
void CommandThread()
{
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    char line[512];
    while (fgets(line, sizeof(line), stdin))
    {
        std::istringstream in(line);
        std::string cmd;
        in >> cmd;
        if (cmd == "gain")
        {
            float g = 1.0f;
            if (in >> g)
                g_gain.store(std::clamp(g, 0.0f, 64.0f));
        }
        else if (cmd == "duck")
        {
            float vol = 1.0f, g = 1.0f;
            in >> vol >> g;
            std::set<DWORD> pids;
            unsigned long pid;
            while (in >> pid)
                pids.insert(static_cast<DWORD>(pid));
            SetVolume(vol, pids, false);       // volume and gain change back to back, in this one thread
            g_gain.store(std::clamp(g, 0.0f, 64.0f));
        }
    }
}

class ActivateHandler : public IActivateAudioInterfaceCompletionHandler, public IAgileObject
{
    LONG ref_ = 1;

public:
    HANDLE done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HRESULT result = E_FAIL;
    IAudioClient* client = nullptr;

    STDMETHODIMP QueryInterface(REFIID riid, void** out) override
    {
        if (riid == __uuidof(IUnknown) || riid == __uuidof(IActivateAudioInterfaceCompletionHandler))
            *out = static_cast<IActivateAudioInterfaceCompletionHandler*>(this);
        else if (riid == __uuidof(IAgileObject))
            *out = static_cast<IAgileObject*>(this);
        else
        {
            *out = nullptr;
            return E_NOINTERFACE;
        }
        AddRef();
        return S_OK;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref_); }
    STDMETHODIMP_(ULONG) Release() override
    {
        ULONG r = InterlockedDecrement(&ref_);
        if (!r)
            delete this;
        return r;
    }
    STDMETHODIMP ActivateCompleted(IActivateAudioInterfaceAsyncOperation* op) override
    {
        HRESULT activate = E_FAIL;
        IUnknown* unk = nullptr;
        HRESULT hr = op->GetActivateResult(&activate, &unk);
        if (SUCCEEDED(hr) && SUCCEEDED(activate) && unk)
        {
            unk->QueryInterface(__uuidof(IAudioClient), reinterpret_cast<void**>(&client));
            unk->Release();
        }
        result = SUCCEEDED(hr) ? activate : hr;
        SetEvent(done);
        return S_OK;
    }
};

int Capture(DWORD pid, bool exclude, DWORD parentPid)
{
    _setmode(_fileno(stdout), _O_BINARY);
    AUDIOCLIENT_ACTIVATION_PARAMS params{};
    params.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK;
    params.ProcessLoopbackParams.TargetProcessId = pid;
    params.ProcessLoopbackParams.ProcessLoopbackMode =
        exclude ? PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE : PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE;

    PROPVARIANT pv{};
    pv.vt = VT_BLOB;
    pv.blob.cbSize = sizeof(params);
    pv.blob.pBlobData = reinterpret_cast<BYTE*>(&params);

    auto* handler = new ActivateHandler();
    IActivateAudioInterfaceAsyncOperation* op = nullptr;
    HRESULT hr = ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, __uuidof(IAudioClient), &pv,
                                             handler, &op);
    if (FAILED(hr))
    {
        fprintf(stderr, "ActivateAudioInterfaceAsync failed: 0x%08lx\n", static_cast<unsigned long>(hr));
        return 2;
    }
    WaitForSingleObject(handler->done, 5000);
    if (FAILED(handler->result) || !handler->client)
    {
        fprintf(stderr, "Process loopback activation failed: 0x%08lx\n", static_cast<unsigned long>(handler->result));
        return 3;
    }
    IAudioClient* client = handler->client;

    WAVEFORMATEX fmt{};
    fmt.wFormatTag = WAVE_FORMAT_PCM;
    fmt.nChannels = 2;
    fmt.nSamplesPerSec = 44100;
    fmt.wBitsPerSample = 16;
    fmt.nBlockAlign = fmt.nChannels * fmt.wBitsPerSample / 8;
    fmt.nAvgBytesPerSec = fmt.nSamplesPerSec * fmt.nBlockAlign;

    hr = client->Initialize(AUDCLNT_SHAREMODE_SHARED,
                            AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK |
                                AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
                            2000000 /* 200 ms */, 0, &fmt, nullptr);
    if (FAILED(hr))
    {
        fprintf(stderr, "IAudioClient::Initialize failed: 0x%08lx\n", static_cast<unsigned long>(hr));
        return 4;
    }
    HANDLE ev = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    client->SetEventHandle(ev);
    IAudioCaptureClient* capture = nullptr;
    hr = client->GetService(__uuidof(IAudioCaptureClient), reinterpret_cast<void**>(&capture));
    if (FAILED(hr) || FAILED(client->Start()))
    {
        fprintf(stderr, "Could not start capture\n");
        return 5;
    }

    // If the program that started us is gone, quit (nobody is reading our output any more).
    HANDLE parent = parentPid ? OpenProcess(SYNCHRONIZE, FALSE, parentPid) : nullptr;
    std::thread(CommandThread).detach();
    std::vector<BYTE> scaled;

    std::vector<BYTE> silence;
    for (;;)
    {
        DWORD w = WaitForSingleObject(ev, 500);
        if (w == WAIT_FAILED)
            return 6;
        if (parent && WaitForSingleObject(parent, 0) == WAIT_OBJECT_0)
            return 0;
        UINT32 packet = 0;
        for (;;)
        {
            HRESULT hrp = capture->GetNextPacketSize(&packet);
            if (FAILED(hrp))
                return 8; // device changed/removed: exit so the caller restarts us
            if (packet == 0)
                break;
            BYTE* data = nullptr;
            UINT32 frames = 0;
            DWORD flags = 0;
            if (FAILED(capture->GetBuffer(&data, &frames, &flags, nullptr, nullptr)))
                return 7;
            const size_t bytes = static_cast<size_t>(frames) * fmt.nBlockAlign;
            bool ok;
            if (flags & AUDCLNT_BUFFERFLAGS_SILENT)
            {
                silence.assign(bytes, 0);
                ok = fwrite(silence.data(), 1, bytes, stdout) == bytes;
            }
            else
            {
                const float g = g_gain.load();
                if (g != 1.0f)
                {
                    scaled.assign(data, data + bytes);
                    auto* samples = reinterpret_cast<int16_t*>(scaled.data());
                    for (size_t i = 0; i < bytes / 2; ++i)
                        samples[i] = static_cast<int16_t>(std::clamp(samples[i] * g, -32768.0f, 32767.0f));
                    ok = fwrite(scaled.data(), 1, bytes, stdout) == bytes;
                }
                else
                    ok = fwrite(data, 1, bytes, stdout) == bytes;
            }
            capture->ReleaseBuffer(frames);
            if (!ok)
                return 0; // parent closed the pipe: we're done
            fflush(stdout);
        }
    }
}

int ListSessions()
{
    IMMDeviceEnumerator* en = nullptr;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator),
                                reinterpret_cast<void**>(&en))))
        return 2;
    IMMDevice* dev = nullptr;
    if (FAILED(en->GetDefaultAudioEndpoint(eRender, eMultimedia, &dev)))
        return 3;
    IAudioSessionManager2* mgr = nullptr;
    if (FAILED(dev->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, reinterpret_cast<void**>(&mgr))))
        return 4;
    IAudioSessionEnumerator* se = nullptr;
    if (FAILED(mgr->GetSessionEnumerator(&se)))
        return 5;
    int count = 0;
    se->GetCount(&count);
    for (int i = 0; i < count; ++i)
    {
        IAudioSessionControl* ctl = nullptr;
        if (FAILED(se->GetSession(i, &ctl)))
            continue;
        IAudioSessionControl2* ctl2 = nullptr;
        if (SUCCEEDED(ctl->QueryInterface(__uuidof(IAudioSessionControl2), reinterpret_cast<void**>(&ctl2))))
        {
            DWORD pid = 0;
            ctl2->GetProcessId(&pid);
            AudioSessionState state = AudioSessionStateInactive;
            ctl->GetState(&state);
            float peak = 0.0f;
            IAudioMeterInformation* meter = nullptr;
            if (SUCCEEDED(ctl->QueryInterface(__uuidof(IAudioMeterInformation), reinterpret_cast<void**>(&meter))))
            {
                meter->GetPeakValue(&peak);
                meter->Release();
            }
            printf("%lu %d %.4f\n", static_cast<unsigned long>(pid), static_cast<int>(state), peak);
            ctl2->Release();
        }
        ctl->Release();
    }
    fflush(stdout);
    return 0;
}

int SetVolume(float volume, const std::set<DWORD>& pids, bool print)
{
    IMMDeviceEnumerator* en = nullptr;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator),
                                reinterpret_cast<void**>(&en))))
        return 2;
    IMMDevice* dev = nullptr;
    if (FAILED(en->GetDefaultAudioEndpoint(eRender, eMultimedia, &dev)))
        return 3;
    IAudioSessionManager2* mgr = nullptr;
    if (FAILED(dev->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, reinterpret_cast<void**>(&mgr))))
        return 4;
    IAudioSessionEnumerator* se = nullptr;
    if (FAILED(mgr->GetSessionEnumerator(&se)))
        return 5;
    int count = 0;
    se->GetCount(&count);
    for (int i = 0; i < count; ++i)
    {
        IAudioSessionControl* ctl = nullptr;
        if (FAILED(se->GetSession(i, &ctl)))
            continue;
        IAudioSessionControl2* ctl2 = nullptr;
        if (SUCCEEDED(ctl->QueryInterface(__uuidof(IAudioSessionControl2), reinterpret_cast<void**>(&ctl2))))
        {
            DWORD pid = 0;
            ctl2->GetProcessId(&pid);
            if (pids.count(pid))
            {
                ISimpleAudioVolume* sv = nullptr;
                if (SUCCEEDED(ctl->QueryInterface(__uuidof(ISimpleAudioVolume), reinterpret_cast<void**>(&sv))))
                {
                    float prev = 1.0f;
                    sv->GetMasterVolume(&prev);
                    if (volume >= 0.0f)
                        sv->SetMasterVolume(volume, nullptr);
                    if (print)
                        printf("%lu %.3f\n", static_cast<unsigned long>(pid), prev);
                    sv->Release();
                }
            }
            ctl2->Release();
        }
        ctl->Release();
    }
    if (print)
        fflush(stdout);
    return 0;
}
} // namespace

int wmain(int argc, wchar_t** argv)
{
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (argc >= 2 && wcscmp(argv[1], L"sessions") == 0)
        return ListSessions();
    if (argc >= 3 && wcscmp(argv[1], L"capture") == 0)
    {
        bool exclude = false;
        DWORD parentPid = 0;
        for (int i = 3; i < argc; ++i)
        {
            if (wcscmp(argv[i], L"exclude") == 0)
                exclude = true;
            else if (wcscmp(argv[i], L"--parent") == 0 && i + 1 < argc)
                parentPid = static_cast<DWORD>(wcstoul(argv[++i], nullptr, 10));
        }
        return Capture(static_cast<DWORD>(wcstoul(argv[2], nullptr, 10)), exclude, parentPid);
    }
    if (argc >= 4 && wcscmp(argv[1], L"volume") == 0)
    {
        std::set<DWORD> pids;
        for (int i = 3; i < argc; ++i)
            pids.insert(static_cast<DWORD>(wcstoul(argv[i], nullptr, 10)));
        return SetVolume(static_cast<float>(wcstod(argv[2], nullptr)), pids, true);
    }
    fprintf(stderr, "usage: NeonDialAudio sessions | capture <pid> [exclude] | volume <0..1> <pid>...\n");
    return 1;
}
