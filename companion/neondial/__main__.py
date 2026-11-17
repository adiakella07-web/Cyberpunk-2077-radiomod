import argparse
import asyncio
import os
import pathlib
import subprocess
import sys
import threading
import time

import psutil

from aiohttp import web

from . import config as config_mod
from .audio import AudioEngine
from .log import RedactingFile, log
from .tasks import spawn
from . import bridge
from .server import build_app, make_stream_handler


def _fix_stdio():
    """Windowed (no-console) builds have no stdout; log to a file instead (size-capped, scrubbed of account details)."""
    if sys.stdout is None or sys.stderr is None:
        config_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = config_mod.DATA_DIR / "companion.log"
        try:
            if path.exists() and path.stat().st_size > 1_000_000:
                path.write_text("")
        except OSError:
            pass
        f = open(path, "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = RedactingFile(f)


def _bind_children_to_us():
    """Windows: put this program in a job object that kills every child (audio helper, Spotify receiver) when it exits,
    even if it is killed from Task Manager, so nothing is left running (or advertising on your network) afterwards."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("a", "b", "c", "d", "e", "f")]

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.windll.kernel32
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        job = k32.CreateJobObjectW(None, None)
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))   # JobObjectExtendedLimitInformation
        k32.AssignProcessToJobObject(job, k32.GetCurrentProcess())
        globals()["_JOB"] = job                                 # keep the handle open for the life of the process
    except Exception as e:                                      # best effort only
        log(f"couldn't set up child cleanup: {type(e).__name__}")


GUI = {"want": threading.Event(), "ready": threading.Event()}


def run_gui():
    """Embedded browser loop (needed for the standalone Apple Music mode). Must run on the main thread."""
    try:
        import webview
    except Exception as e:
        log(f"built-in browser unavailable: {e}")
        return
    os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--autoplay-policy=no-user-gesture-required")
    webview.create_window("Neon Dial host", html="<html></html>", hidden=True)   # keeps the loop alive
    webview.start(lambda: GUI["ready"].set(), private_mode=False, storage_path=str(config_mod.DATA_DIR / "webview"))


def make_provider(cfg, engine):
    name = cfg["provider"]
    if name == "apple-standalone":
        from .providers.applemusic import AppleWebProvider
        return AppleWebProvider(cfg, engine, GUI)
    if name == "demo":
        from .providers.demo import DemoProvider
        return DemoProvider(cfg, engine)
    if name == "standalone":
        from .providers.standalone import StandaloneProvider
        return StandaloneProvider(cfg, engine)
    from .providers.system import SystemProvider
    return SystemProvider(cfg, engine)


async def watch_pid(pid, shutdown):
    """Exit (cleanly) when the game process is gone."""
    while psutil.pid_exists(pid):
        await asyncio.sleep(1)
    await shutdown()


async def watch_game(name, shutdown):
    seen, start = False, time.time()
    while True:
        running = any((p.info["name"] or "").lower() == name.lower() for p in psutil.process_iter(["name"]))
        if running:
            seen = True
        elif seen or time.time() - start > 300:
            await shutdown()
        await asyncio.sleep(2)


async def serve(cfg, engine, provider, ready, watch, watch_pid_arg=None):
    app = build_app(cfg, engine, provider)

    async def shutdown():
        try:
            await asyncio.wait_for(app["hub"].provider.stop(), 6)   # restores the music app's volume, stops capture
        except Exception:
            pass
        finally:
            os._exit(0)
    app["shutdown"] = shutdown

    async def switch(mode):
        if mode not in config_mod.ALLOWED["provider"]:
            raise ValueError("unknown mode")
        hub = app["hub"]
        try:
            await asyncio.wait_for(hub.provider.stop(), 6)
        except Exception as e:
            log(f"stopping the old mode: {type(e).__name__}")
        cfg["provider"] = mode
        engine.hold = False
        engine.flush()
        new = make_provider(cfg, engine)
        hub.provider = new
        try:
            await new.start()
            if hub.tuned:
                await new.play()
        except Exception as e:
            log(f"starting {mode}: {type(e).__name__}: {e}")
    app["switch"] = switch
    runner = web.AppRunner(app)
    await runner.setup()
    # 127.0.0.1 only: nothing on your network can reach this.
    try:
        if cfg.get("web_panel"):                      # optional browser page, off by default
            await web.TCPSite(runner, "127.0.0.1", cfg["port"]).start()
        await asyncio.start_server(make_stream_handler(engine, app["hub"]), "127.0.0.1", cfg["stream_port"])
    except OSError:
        print("Port in use - another Neon Dial companion is probably already running.")
        return
    engine.texture.set_mode(cfg.get("texture", "off"))
    mod_dir = bridge.find_mod_dir()
    if mod_dir:
        spawn(bridge.run(app, engine, mod_dir))
    await provider.start()
    base = f"http://127.0.0.1:{cfg['port']}"
    print(f"Neon Dial companion running ({provider.name}). Stream: http://127.0.0.1:{cfg['stream_port']}/Neon_Dial_Your_Music.mp3"
          + (f"  Panel: {base}/" if cfg.get("web_panel") else ""))
    ready.set()
    if watch:
        spawn(watch_game(cfg["game_process"], shutdown))
    if watch_pid_arg:
        spawn(watch_pid(watch_pid_arg, shutdown))
    try:
        await engine.run()
    finally:
        await provider.stop()
        await runner.cleanup()


def selftest(path):
    """Used by CI (and for support): checks the packaged app really works, writes a report to `path`."""
    import traceback
    lines, ok = [], True

    def log_(x):
        lines.append(str(x))

    try:
        from .providers import system as sysmod
        from .server import WEB
        log_(f"frozen={getattr(sys, 'frozen', False)} python={sys.version.split()[0]}")
        log_(f"winrt media-control available: {sysmod.AVAILABLE}")
        ok &= sysmod.AVAILABLE
        helper = sysmod.helper_path()
        log_(f"audio helper: {helper}")
        ok &= helper is not None
        log_(f"web ui present: {(WEB / 'index.html').exists()}")
        ok &= (WEB / "index.html").exists()
        import aiohttp
        import lameenc  # noqa: F401
        from .providers.standalone import StandaloneProvider, librespot_path
        StandaloneProvider({}, AudioEngine())
        log_(f"standalone provider ok; librespot present: {librespot_path()}")
        from .dsp import Texture
        tx = Texture()
        tx.set_mode("radio")
        log_(f"texture dsp ok: {len(tx.process(bytes(17640)))} bytes")

        async def go():
            cfg = config_mod.load()
            cfg["port"], cfg["provider"], cfg["stream_port"], cfg["web_panel"] = 8799, "system", 8798, True
            engine = AudioEngine()
            provider = make_provider(cfg, engine)
            task = asyncio.create_task(serve(cfg, engine, provider, threading.Event(), False))
            await asyncio.sleep(1.5)
            async with aiohttp.ClientSession() as sess:
                if sysmod.AVAILABLE:
                    mgr = await sysmod.Manager.request_async()
                    log_(f"SMTC sessions visible: {len(list(mgr.get_sessions()))}")
                rd, wr = await asyncio.open_connection("127.0.0.1", cfg["stream_port"])
                wr.write(b"GET /Neon_Dial_Your_Music.mp3 HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
                await wr.drain()
                data = await asyncio.wait_for(rd.readexactly(20000), 6)
                log_(f"stream first line: {data.split(b'\r\n')[0].decode()} ; bytes: {len(data)} ; chunked={b'chunked' in data[:300].lower()}")
                ok_stream = data.startswith(b"HTTP/1.0 200") and b"chunked" not in data[:300].lower()
                wr.close()
                await asyncio.sleep(1.0)
                st = await (await sess.get("http://127.0.0.1:8799/api/state")).json()
                log_(f"state: tuned_in={st.get('tuned_in')} error={st.get('error')} output={st.get('output')} helper_found={st.get('helper_found')}")
            task.cancel()
            return ok_stream

        ok &= bool(asyncio.run(go()))
        if helper:
            for args in (["sessions"], ["volume", "1.0", "0"], ["capture", "0"]):
                try:
                    r = subprocess.run([str(helper), *args], capture_output=True, text=True, timeout=8)
                    log_(f"helper {' '.join(args)} -> rc={r.returncode} {r.stderr.strip()[:150]}")
                except subprocess.TimeoutExpired:
                    log_(f"helper {' '.join(args)} -> still running after 8s (ok for capture)")
    except Exception:
        ok = False
        log_(traceback.format_exc())
    try:
        import tempfile
        import webview
        res = {}

        def work():
            try:
                res["r"] = win.evaluate_js("(function(){return JSON.stringify(MusicKit.getInstance().isPlaying)})()")
            except Exception as e:
                res["err"] = repr(e)
            finally:
                win.destroy()
        threading.Timer(60, lambda: os._exit(1)).start()
        win = webview.create_window("t", html="<script>window.MusicKit={getInstance:function(){return {isPlaying:false}}}</script>", hidden=True)
        webview.start(work, private_mode=False, storage_path=tempfile.mkdtemp())
        log_(f"built-in browser (WebView2) check: {'OK ' + str(res.get('r')) if 'r' in res else 'FAILED ' + str(res.get('err'))}")
    except Exception as e:
        log_(f"built-in browser (WebView2) check: FAILED {e!r}")
    pathlib.Path(path).write_text("\n".join(lines) + ("\nSELFTEST OK" if ok else "\nSELFTEST FAILED"), encoding="utf-8")
    os._exit(0 if ok else 1)


def cli():
    _fix_stdio()
    _bind_children_to_us()
    ap = argparse.ArgumentParser(prog="NeonDial")
    ap.add_argument("--config", help="optional config.toml")
    ap.add_argument("--provider", help="override provider: apple | spotify | demo")
    ap.add_argument("--selftest", metavar="REPORT_FILE", help="run a self-check and write a report")
    ap.add_argument("--watch-pid", type=int, help="quit cleanly when this process (the game) exits")
    ap.add_argument("--watch-game", action="store_true", help="quit automatically when the game closes")
    args = ap.parse_args()
    if args.selftest:
        selftest(args.selftest)
    config_mod.finish_pending_wipe()
    cfg = config_mod.load(args.config)
    if args.provider:
        cfg["provider"] = args.provider
    cfg["game_pid"] = args.watch_pid

    engine = AudioEngine()
    provider = make_provider(cfg, engine)
    t = threading.Thread(
        target=lambda: asyncio.run(serve(cfg, engine, provider, threading.Event(), args.watch_game, args.watch_pid)),
        daemon=True)
    t.start()
    while t.is_alive():
        if GUI["want"].wait(0.5):
            run_gui()
            break
    t.join()


if __name__ == "__main__":
    cli()
