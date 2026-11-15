import asyncio
import os
import pathlib

from aiohttp import web

from . import config as config_mod
from .providers import ProviderError

WEB = pathlib.Path(__file__).parent / "web"


class Hub:
    """Tracks who is listening to /stream.mp3. First listener = you tuned in to the
    station in-game -> provider.play(). Last listener gone -> provider.pause() after a short grace."""

    def __init__(self, cfg, provider):
        self.provider = provider
        self.idle = cfg["idle_pause_seconds"]
        self.listeners = 0
        self.tuned = False
        self.error = None
        self._idle_task = None
        self._lock = asyncio.Lock()

    def connected(self):
        self.listeners += 1
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None
        if not self.tuned:
            asyncio.create_task(self._set(True))

    def disconnected(self):
        self.listeners = max(0, self.listeners - 1)
        if self.listeners == 0 and self.tuned:
            self._idle_task = asyncio.create_task(self._idle_pause())

    async def _idle_pause(self):
        await asyncio.sleep(self.idle)
        if self.listeners == 0:
            await self._set(False)

    async def _set(self, on):
        async with self._lock:
            self.tuned = on
            try:
                await (self.provider.play() if on else self.provider.pause())
                self.error = None
            except ProviderError as e:
                self.error = str(e)
                print("[hub]", e)
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"
                print("[hub]", self.error)


def build_app(cfg, engine, provider):
    hub = Hub(cfg, provider)
    app = web.Application()

    async def stream(request):
        resp = web.StreamResponse(headers={
            "Content-Type": "audio/mpeg", "Cache-Control": "no-cache, no-store", "icy-name": "Neon Dial"})
        await resp.prepare(request)
        await resp.write(engine.preroll)
        q = engine.add_client()
        hub.connected()
        try:
            while True:
                await resp.write(await q.get())
        except (ConnectionResetError, ConnectionError):
            pass
        finally:
            engine.remove_client(q)
            hub.disconnected()
        return resp

    async def index(_):
        return web.FileResponse(WEB / "index.html")

    async def state(_):
        if hasattr(provider, "refresh"):
            await provider.refresh()
        s = {"provider": provider.name, "tuned_in": hub.tuned, "listeners": hub.listeners, "error": hub.error}
        s.update(provider.state())
        return web.json_response(s)

    def guarded(fn):
        async def handler(request):
            try:
                return web.json_response(await fn(request))
            except ProviderError as e:
                return web.json_response({"error": str(e)}, status=400)
            except Exception as e:
                return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=500)
        return handler

    async def control(request):
        action = (await request.json()).get("action")
        if action == "next":
            await provider.next()
        elif action == "prev":
            await provider.prev()
        elif action == "play":
            await hub._set(True)
        elif action == "pause":
            await hub._set(False)
        else:
            raise ProviderError("unknown action")
        return {"ok": True}

    async def set_app(request):
        app_name = ((await request.json()).get("music_app") or "auto").strip().lower()
        config_mod.save_settings({"music_app": app_name})
        provider.pref = app_name
        return {"ok": True}

    async def set_output(request):
        mode = (await request.json()).get("output")
        if mode not in ("game", "speakers"):
            raise ProviderError("output must be game or speakers")
        config_mod.save_settings({"output": mode})
        await provider.set_output(mode)
        return {"ok": True}

    async def quit_app(_):
        asyncio.create_task(app["shutdown"]())
        return {"ok": True}

    app.add_routes([
        web.get("/", index), web.get("/{name}.mp3", stream), web.get("/api/state", state),
        web.post("/api/control", guarded(control)), web.post("/api/music_app", guarded(set_app)),
        web.post("/api/output", guarded(set_output)), web.post("/api/quit", guarded(quit_app)),
    ])
    return app
