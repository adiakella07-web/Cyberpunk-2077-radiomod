import asyncio
import os
import pathlib

from aiohttp import web

from . import config as config_mod
from .log import log, recent
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
        log(f"game connected to the stream (listeners={self.listeners})")
        if not self.tuned:
            asyncio.create_task(self._set(True))

    def disconnected(self):
        self.listeners = max(0, self.listeners - 1)
        log(f"game disconnected from the stream (listeners={self.listeners})")
        if self.listeners == 0 and self.tuned:
            self._idle_task = asyncio.create_task(self._idle_pause())

    async def _idle_pause(self):
        await asyncio.sleep(self.idle)
        if self.listeners == 0:
            await self._set(False)

    async def _set(self, on):
        async with self._lock:
            self.tuned = on
            log("tuned in -> play" if on else "tuned out -> pause")
            try:
                await (self.provider.play() if on else self.provider.pause())
                self.error = None
            except ProviderError as e:
                self.error = str(e)
                log(f"error: {e}")
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"
                log(f"error: {self.error}")


ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
MAX_STREAM_CLIENTS = 6


def make_stream_handler(engine, hub):
    """Plain Icecast-style stream (HTTP/1.0, no chunking): what the game's FMOD audio engine expects."""
    async def handle(reader, writer):
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
        except Exception:
            writer.close()
            return
        method = head.split(b" ", 1)[0]
        # Only the game's own audio engine should ever read this stream. Browsers (any web page you visit) always send
        # Fetch-Metadata / Origin / Referer headers, and a DNS-rebinding page sends a foreign Host: refuse all of those.
        names = {ln.split(b":", 1)[0].strip().lower(): ln.split(b":", 1)[1].strip().lower()
                 for ln in head.split(b"\r\n")[1:] if b":" in ln}
        host = names.get(b"host", b"127.0.0.1").decode(errors="replace").split(":")[0]
        if (any(n.startswith(b"sec-fetch-") for n in names) or b"origin" in names or b"referer" in names
                or host not in ALLOWED_HOSTS or len(engine.clients) >= MAX_STREAM_CLIENTS):
            writer.write(b"HTTP/1.0 403 Forbidden\r\nConnection: close\r\n\r\n")
            try:
                await writer.drain()
            finally:
                writer.close()
            return
        writer.write(b"HTTP/1.0 200 OK\r\nContent-Type: audio/mpeg\r\nicy-name: Neon Dial FM\r\n"
                     b"icy-br: 320\r\nCache-Control: no-cache\r\nConnection: close\r\n\r\n")
        if method != b"GET":
            await writer.drain()
            writer.close()
            return
        writer.write(engine.preroll)
        q = engine.add_client()
        hub.connected()
        try:
            while True:
                writer.write(await q.get())
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            engine.remove_client(q)
            hub.disconnected()
            try:
                writer.close()
            except Exception:
                pass
    return handle


@web.middleware
async def guard(request, handler):
    """The optional web page is a local control surface: refuse anything that doesn't come from itself."""
    port = request.app["port"]
    host = request.headers.get("Host", "").split(":")[0].lower()
    if host not in ALLOWED_HOSTS:
        return web.Response(status=403, text="forbidden")
    site = request.headers.get("Sec-Fetch-Site")
    if site and site not in ("same-origin", "none"):
        return web.Response(status=403, text="forbidden")
    origin = request.headers.get("Origin")
    if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
        return web.Response(status=403, text="forbidden")
    if request.method not in ("GET", "HEAD") and request.content_type != "application/json":
        return web.Response(status=415, text="json only")
    resp = await handler(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                               "connect-src 'self'; img-src data:; frame-ancestors 'none'")
    return resp


def build_app(cfg, engine, provider):
    hub = Hub(cfg, provider)
    app = web.Application(middlewares=[guard])
    app["port"] = cfg["port"]

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
        if hasattr(hub.provider, "refresh"):
            await hub.provider.refresh()
        s = {"texture": engine.texture.mode, "provider": hub.provider.name, "tuned_in": hub.tuned, "listeners": hub.listeners, "error": hub.error,
             "log": recent(15)}
        s.update(hub.provider.state())
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
            await hub.provider.next()
        elif action == "prev":
            await hub.provider.prev()
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
        hub.provider.pref = app_name
        return {"ok": True}

    async def set_output(request):
        mode = (await request.json()).get("output")
        if mode not in ("game", "speakers"):
            raise ProviderError("output must be game or speakers")
        config_mod.save_settings({"output": mode})
        await hub.provider.set_output(mode)
        return {"ok": True}

    async def set_mode(request):
        mode = (await request.json()).get("mode")
        if mode not in ("system", "standalone", "apple-standalone"):
            raise ProviderError("unknown mode")
        config_mod.save_settings({"provider": mode})
        await app["switch"](mode)
        return {"ok": True}

    async def window(request):
        hub.provider.show_window(bool((await request.json()).get("show")))
        return {"ok": True}

    async def do(key, val):
        """Single entry point for commands coming from the in-game overlay."""
        try:
            if key == "mode":
                config_mod.save_settings({"provider": val})
                await app["switch"](val)
            elif key == "action":
                if val == "next":
                    await hub.provider.next()
                elif val == "prev":
                    await hub.provider.prev()
            elif key == "window":
                hub.provider.show_window(val == "show")
            elif key == "texture":
                engine.texture.set_mode(val)
                config_mod.save_settings({"texture": val})
            elif key == "forget":
                await hub.provider.forget()
                config_mod.wipe_credentials()
                log("signed out: saved logins erased")
            elif key == "output":
                config_mod.save_settings({"output": val})
                await hub.provider.set_output(val)
        except ProviderError as e:
            log(f"{key}: {e}")
        except Exception as e:
            log(f"{key}: {type(e).__name__}: {e}")
    app["do"] = do

    async def set_texture(request):
        mode = (await request.json()).get("texture", "off")
        await do("texture", mode)
        return {"ok": True}

    async def quit_app(_):
        asyncio.create_task(app["shutdown"]())
        return {"ok": True}

    app.add_routes([
        web.get("/", index), web.get("/{name}.mp3", stream), web.get("/api/state", state),
        web.post("/api/control", guarded(control)), web.post("/api/music_app", guarded(set_app)),
        web.post("/api/output", guarded(set_output)), web.post("/api/mode", guarded(set_mode)), web.post("/api/texture", guarded(set_texture)), web.post("/api/window", guarded(window)), web.post("/api/quit", guarded(quit_app)),
    ])
    app["hub"] = hub
    return app
