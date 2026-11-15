import argparse
import asyncio
import os
import subprocess
import sys
import threading
import time

from aiohttp import web

from . import config as config_mod
from .audio import AudioEngine
from .server import build_app


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
    from .providers.system import SystemProvider
    return SystemProvider(cfg, engine)


def game_running(name):
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                             capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return name.lower() in out.lower()
    except Exception:
        return False


async def watch_game(name):
    """Exit when the game closes (or never started), so the companion can auto-launch with it."""
    seen, start = False, time.time()
    while True:
        if await asyncio.to_thread(game_running, name):
            seen = True
        elif seen or time.time() - start > 300:
            os._exit(0)
        await asyncio.sleep(5)


async def serve(cfg, engine, provider, ready, watch):
    app = build_app(cfg, engine, provider)
    runner = web.AppRunner(app)
    await runner.setup()
    # 127.0.0.1 only: nothing on your network can reach this.
    try:
        await web.TCPSite(runner, "127.0.0.1", cfg["port"]).start()
    except OSError:
        print("Port in use - another Neon Dial companion is probably already running.")
        return
    await provider.start()
    base = f"http://127.0.0.1:{cfg['port']}"
    print(f"Neon Dial companion running ({provider.name}). Stream: {base}/stream.mp3  Panel: {base}/")
    ready.set()
    if watch:
        asyncio.create_task(watch_game(cfg["game_process"]))
    try:
        await engine.run()
    finally:
        await provider.stop()
        await runner.cleanup()


def cli():
    _fix_stdio()
    ap = argparse.ArgumentParser(prog="NeonDial")
    ap.add_argument("--config", help="optional config.toml")
    ap.add_argument("--provider", help="override provider: apple | spotify | demo")
    ap.add_argument("--watch-game", action="store_true", help="quit automatically when the game closes")
    args = ap.parse_args()
    cfg = config_mod.load(args.config)
    if args.provider:
        cfg["provider"] = args.provider

    engine = AudioEngine()
    provider = make_provider(cfg, engine)
    ready = threading.Event()
    asyncio.run(serve(cfg, engine, provider, threading.Event(), args.watch_game))


if __name__ == "__main__":
    cli()
