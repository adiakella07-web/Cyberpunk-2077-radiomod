"""Run with: python -m pytest tests -q   (from the repository root; needs the companion requirements)"""
import asyncio
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "companion"))

from neondial import config as C  # noqa: E402
from neondial.audio import AudioEngine  # noqa: E402
from neondial.log import redact  # noqa: E402
from neondial.providers import Provider, ProviderError  # noqa: E402
from neondial.server import Hub, make_stream_handler  # noqa: E402


def test_redaction_hides_accounts_and_secrets():
    cases = {
        "Authenticated as john.doe@example.com": "john.doe",
        "token=abcdef123456": "abcdef123456",
        "Browse to: https://accounts.spotify.com/authorize?code_challenge=xyz": "code_challenge",
        "key 0123456789abcdef0123456789abcdef0123": "0123456789abcdef",
        "C:\\Users\\Some Person\\AppData\\x": "Some Person",
        "cookie: sessionid=XYZ": "XYZ",
        "loaded D:\\Games\\Cyberpunk 2077\\bin\\x64\\plugins\\x.dll ok": "Cyberpunk",
        "file \\\\server\\share\\music\\a.mp3": "share",
        "path /home/someone/.neondial/x": "someone",
    }
    for text, secret in cases.items():
        assert secret not in redact(text), text
    assert redact("capture failed: 0x80070057") == "capture failed: 0x80070057"


def test_config_rejects_bad_values():
    bad = {"provider": "evil", "texture": "x", "port": 80, "stream_port": "9", "web_panel": "yes",
           "idle_pause_seconds": -4, "game_process": "..\\evil.exe", "output": 5}
    clean = C.sanitize(bad)
    assert clean["provider"] == "system" and clean["texture"] == "off" and clean["port"] == 8765
    assert clean["stream_port"] == 8766 and clean["web_panel"] is False and clean["idle_pause_seconds"] == 1.0
    assert clean["game_process"] == "Cyberpunk2077.exe" and clean["output"] == "game"


class FakeProvider(Provider):
    name = "fake"

    def __init__(self):
        self.calls = []
        self.playing = False

    async def play(self):
        await asyncio.sleep(0.05)
        self.calls.append("play")
        self.playing = True

    async def pause(self):
        await asyncio.sleep(0.3)                    # slow pause, like a real app
        self.calls.append("pause")
        self.playing = False


async def _raw(port, req):
    r, w = await asyncio.open_connection("127.0.0.1", port)
    w.write(req)
    await w.drain()
    d = await asyncio.wait_for(r.read(200), 3)
    w.close()
    return d.split(b"\r\n")[0].decode()


def test_stream_refuses_browsers_and_foreign_hosts():
    async def main():
        engine, hub = AudioEngine(), Hub({"idle_pause_seconds": 0.1}, FakeProvider())
        srv = await asyncio.start_server(make_stream_handler(engine, hub), "127.0.0.1", 8841)
        ok = await _raw(8841, b"GET /a.mp3 HTTP/1.0\r\nHost: 127.0.0.1:8841\r\n\r\n")
        sec = await _raw(8841, b"GET /a.mp3 HTTP/1.1\r\nHost: 127.0.0.1\r\nSec-Fetch-Site: cross-site\r\n\r\n")
        org = await _raw(8841, b"GET /a.mp3 HTTP/1.1\r\nHost: 127.0.0.1\r\nOrigin: https://evil.example\r\n\r\n")
        rebind = await _raw(8841, b"GET /a.mp3 HTTP/1.1\r\nHost: evil.example\r\n\r\n")
        srv.close()
        return ok, sec, org, rebind
    ok, sec, org, rebind = asyncio.run(main())
    assert "200" in ok and "403" in sec and "403" in org and "403" in rebind


def test_quick_retune_never_leaves_music_paused():
    """Tune out, then back in while the (slow) pause is still running: the end state must be 'playing'."""
    async def main():
        prov = FakeProvider()
        hub = Hub({"idle_pause_seconds": 0.05}, prov)
        hub.connected()
        await asyncio.sleep(0.2)                     # playing
        hub.disconnected()
        await asyncio.sleep(0.15)                    # idle grace over, slow pause in progress
        hub.connected()                              # listener is back
        await asyncio.sleep(1.2)
        return prov.playing, hub.tuned
    playing, tuned = asyncio.run(main())
    assert playing and tuned


def test_source_not_ready_is_retried():
    class Flaky(FakeProvider):
        n = 0

        async def play(self):
            Flaky.n += 1
            if Flaky.n < 2:
                raise ProviderError("still loading")
            await super().play()

    async def main():
        prov = Flaky()
        hub = Hub({"idle_pause_seconds": 0.05}, prov)
        hub.connected()
        await asyncio.sleep(3.5)
        return prov.playing
    assert asyncio.run(main())
