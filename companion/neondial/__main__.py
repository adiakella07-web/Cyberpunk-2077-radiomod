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
from .log import log
from .server import build_app, make_stream_handler


def _fix_stdio():
    """Windowed (no-console) builds have no stdout; log to a file instead."""
    if sys.stdout is None or sys.stderr is None:
        config_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        f = open(config_mod.DATA_DIR / "companion.log", "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = f


def make_provider(cfg, engine):
    name = cfg["provider"]
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
            await provider.stop()      # restores the music app's volume, stops capture
        finally:
            os._exit(0)
    app["shutdown"] = shutdown

    async def switch(mode):
        hub = app["hub"]
        await hub.provider.stop()
        cfg["provider"] = mode
        engine.hold = False
        engine.flush()
        new = make_provider(cfg, engine)
        hub.provider = new
        await new.start()
        if hub.tuned:
            await new.play()
    app["switch"] = switch
    runner = web.AppRunner(app)
    await runner.setup()
    # 127.0.0.1 only: nothing on your network can reach this.
    try:
        await web.TCPSite(runner, "127.0.0.1", cfg["port"]).start()
    except OSError:
        print("Port in use - another Neon Dial companion is probably already running.")
        return
    await asyncio.start_server(make_stream_handler(engine, app["hub"]), "127.0.0.1", cfg["stream_port"])
    await provider.start()
    base = f"http://127.0.0.1:{cfg['port']}"
    print(f"Neon Dial companion running ({provider.name}). Stream: http://127.0.0.1:{cfg['stream_port']}/Neon_Dial_Your_Music.mp3  Panel: {base}/")
    ready.set()
    if watch:
        asyncio.create_task(watch_game(cfg["game_process"], shutdown))
    if watch_pid_arg:
        asyncio.create_task(watch_pid(watch_pid_arg, shutdown))
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

        async def go():
            cfg = config_mod.load()
            cfg["port"], cfg["provider"], cfg["stream_port"] = 8799, "system", 8798
            engine = AudioEngine()
            provider = make_provider(cfg, engine)
            task = asyncio.create_task(serve(cfg, engine, provider, threading.Event(), False))
            await asyncio.sleep(1.5)
            async with aiohttp.ClientSession() as sess:
                if sysmod.AVAILABLE:
                    mgr = await sysmod.Manager.request_async()
                    log_(f"SMTC sessions visible: {len(list(mgr.get_sessions()))}")
                rd, wr = await asyncio.open_connection("127.0.0.1", cfg["stream_port"])
                wr.write(b"GET /Neon_Dial_Your_Music.mp3 HTTP/1.1\r\nHost: x\r\n\r\n")
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
    pathlib.Path(path).write_text("\n".join(lines) + ("\nSELFTEST OK" if ok else "\nSELFTEST FAILED"), encoding="utf-8")
    os._exit(0 if ok else 1)


def cli():
    _fix_stdio()
    ap = argparse.ArgumentParser(prog="NeonDial")
    ap.add_argument("--config", help="optional config.toml")
    ap.add_argument("--provider", help="override provider: apple | spotify | demo")
    ap.add_argument("--selftest", metavar="REPORT_FILE", help="run a self-check and write a report")
    ap.add_argument("--watch-pid", type=int, help="quit cleanly when this process (the game) exits")
    ap.add_argument("--watch-game", action="store_true", help="quit automatically when the game closes")
    args = ap.parse_args()
    if args.selftest:
        selftest(args.selftest)
    cfg = config_mod.load(args.config)
    if args.provider:
        cfg["provider"] = args.provider
    cfg["game_pid"] = args.watch_pid

    engine = AudioEngine()
    provider = make_provider(cfg, engine)
    ready = threading.Event()
    asyncio.run(serve(cfg, engine, provider, threading.Event(), args.watch_game, args.watch_pid))


if __name__ == "__main__":
    cli()
