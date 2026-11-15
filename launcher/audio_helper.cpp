// NeonDialAudio.exe - tiny helper for Neon Dial.
//   NeonDialAudio.exe capture <pid>             raw PCM (S16LE, 44.1 kHz, stereo) of that app (and its child processes)
//                                               to stdout, via Windows process loopback. Needs Windows 10 2004+.
//   NeonDialAudio.exe volume <0..1> <pid>...    set the Windows mixer volume of those apps' sessions; prints "<pid> <previous>"
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <initguid.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audioclientactivationparams.h>
#include <audiopolicy.h>

#include <fcntl.h>
#include <io.h>
#include <cstdio>
#include <cstdlib>
#include <cwchar>
#include <set>
#include <vector>

namespace
{
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

int Capture(DWORD pid)
{
    _setmode(_fileno(stdout), _O_BINARY);
    AUDIOCLIENT_ACTIVATION_PARAMS params{};
    params.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK;
    params.ProcessLoopbackParams.TargetProcessId = pid;
    params.ProcessLoopbackParams.ProcessLoopbackMode = PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE;

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

    std::vector<BYTE> silence;
    for (;;)
    {
        DWORD w = WaitForSingleObject(ev, 500);
        if (w == WAIT_FAILED)
            return 6;
        UINT32 packet = 0;
        while (SUCCEEDED(capture->GetNextPacketSize(&packet)) && packet > 0)
        {
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
                ok = fwrite(data, 1, bytes, stdout) == bytes;
            capture->ReleaseBuffer(frames);
            if (!ok)
                return 0; // parent closed the pipe: we're done
            fflush(stdout);
        }
    }
}

int SetVolume(float volume, const std::set<DWORD>& pids)
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
                    sv->SetMasterVolume(volume, nullptr);
                    printf("%lu %.3f\n", static_cast<unsigned long>(pid), prev);
                    sv->Release();
                }
            }
            ctl2->Release();
        }
        ctl->Release();
    }
    fflush(stdout);
    return 0;
}
} // namespace

int wmain(int argc, wchar_t** argv)
{
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (argc >= 3 && wcscmp(argv[1], L"capture") == 0)
        return Capture(static_cast<DWORD>(wcstoul(argv[2], nullptr, 10)));
    if (argc >= 4 && wcscmp(argv[1], L"volume") == 0)
    {
        std::set<DWORD> pids;
        for (int i = 3; i < argc; ++i)
            pids.insert(static_cast<DWORD>(wcstoul(argv[i], nullptr, 10)));
        return SetVolume(static_cast<float>(wcstod(argv[2], nullptr)), pids);
    }
    fprintf(stderr, "usage: NeonDialAudio capture <pid> | volume <0..1> <pid>...\n");
    return 1;
}
