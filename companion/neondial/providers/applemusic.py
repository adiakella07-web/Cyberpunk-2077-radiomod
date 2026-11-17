"""Standalone Apple Music: no Apple Music app needed.

Neon Dial hosts the Apple Music web player (music.apple.com) in a built-in browser window (Edge WebView2).
You sign in there once and start a playlist, then hide the window. After that:
  * tune in  -> the page's own player is told to play, tune out -> pause (it keeps its place)
  * the page's audio is captured from this program's own browser processes and streamed into the game,
    so it plays through the game's radio mix; its Windows volume is turned down so you don't hear it twice.
No developer account or tokens: it uses the normal Apple Music website with your own login.
"""
import asyncio
import json
import os

import psutil

from ..config import DATA_DIR
from ..log import log
from ..tasks import spawn
from . import ProviderError
from .system import SystemProvider

SITE = "https://music.apple.com/"
# The embedded browser may only be on Apple's own sites (sign-in, the player, its CDNs). If anything sends it elsewhere,
# it is taken straight back, so a stray redirect can never show you a look-alike login page inside Neon Dial.
ALLOWED_SUFFIXES = ("apple.com", "icloud.com", "mzstatic.com", "cdn-apple.com", "apple-musickit.com", "applemusic.com")
HIDDEN_FLAG = DATA_DIR / "apple_window_hidden"
JS_STATUS = ("(function(){try{var m=MusicKit.getInstance();var i=m.nowPlayingItem;"
             "return JSON.stringify({ok:true,playing:!!m.isPlaying,title:i?i.title:'',artist:i?(i.artistName||''):'',"
             "auth:!!m.isAuthorized,hasQueue:!!i});}catch(e){return JSON.stringify({ok:false,err:String(e)});}})()")


class AppleWebProvider(SystemProvider):
    name = "apple-standalone"
    prefer_root = True

    def __init__(self, cfg, engine, gui):
        super().__init__(cfg, engine)
        self.gui = gui
        self.win = None
        self.status = "starting the built-in browser"

    async def start(self):
        await super().start()
        self.gui["want"].set()                       # main thread starts the embedded-browser loop
        spawn(self._open())

    async def stop(self):
        if getattr(self, "_guard", None):
            self._guard.cancel()
        await super().stop()                         # pauses the page if we were tuned in, restores the window's volume

    async def _watch_navigation(self):
        from urllib.parse import urlparse
        while True:
            await asyncio.sleep(0.5)
            try:
                url = await asyncio.to_thread(self.win.get_current_url)
            except Exception:
                continue
            if not url or url.startswith(("about:", "data:")):
                continue
            host = (urlparse(url).hostname or "").lower()
            if not any(host == d or host.endswith("." + d) for d in ALLOWED_SUFFIXES):
                log("the Apple Music window left Apple's sites; taking it back")
                try:
                    await asyncio.to_thread(self.win.load_url, SITE)
                except Exception:
                    pass

    async def forget(self):
        self.status = "signed out: open the Apple sign-in window to log in again"
        if self.win:
            try:
                await asyncio.to_thread(self.win.clear_cookies)
                await asyncio.to_thread(self.win.load_url, SITE)
            except Exception as e:
                log(f"clearing the browser session: {type(e).__name__}")

    async def _open(self):
        if not await asyncio.to_thread(self.gui["ready"].wait, 40):
            self.status = "the built-in browser couldn't start (is Microsoft Edge WebView2 installed?)"
            log(self.status)
            return
        import webview
        show = not HIDDEN_FLAG.exists()
        self.win = webview.create_window("Apple Music - Neon Dial", SITE, width=1100, height=760, hidden=not show)

        def on_closing():
            self.win.hide()                          # keep playing in the background
            HIDDEN_FLAG.write_text("1")
            return False
        self.win.events.closing += on_closing
        self._guard = spawn(self._watch_navigation())
        self.status = ("sign in to Apple Music in the window, start a playlist, then click Hide window"
                       if show else "ready (window hidden): tune in to play")
        log("Apple Music window " + ("shown for sign-in" if show else "created hidden"))

    # ---- page control ----------------------------------------------------
    async def _js(self, code):
        if not self.win:
            raise ProviderError("The Apple Music window isn't ready yet; try again in a few seconds.")
        try:
            return await asyncio.wait_for(asyncio.to_thread(self.win.evaluate_js, code), 8)
        except asyncio.TimeoutError:
            raise ProviderError("The Apple Music page didn't respond.")
        except Exception as e:
            raise ProviderError(f"Apple Music page error: {e}")

    async def _st(self):
        raw = await self._js(JS_STATUS)
        try:
            d = json.loads(raw)
        except Exception:
            raise ProviderError("The Apple Music page isn't ready yet (still loading, or not signed in).")
        if not d.get("ok"):
            raise ProviderError("The Apple Music page isn't ready yet: " + str(d.get("err", ""))[:80])
        return d

    async def _ctl_info(self):
        return "applemusic-web", (await self._st())["playing"]

    async def _ctl_play(self):
        d = await self._st()
        if not d["auth"]:
            raise ProviderError("Sign in to Apple Music in its window first (control panel: Show window).")
        if not d["hasQueue"]:
            raise ProviderError("Start a playlist once in the Apple Music window, then hide it.")
        await self._js("MusicKit.getInstance().play();")
        return True

    async def _ctl_pause(self):
        await self._js("MusicKit.getInstance().pause();")

    async def _ctl_next(self):
        await self._js("MusicKit.getInstance().skipToNextItem();")

    async def _ctl_prev(self):
        await self._js("MusicKit.getInstance().skipToPreviousItem();")

    async def _ctl_now(self):
        d = await self._st()
        return {"title": d["title"], "artist": d["artist"], "playing": d["playing"], "app": "Apple Music (built in)"}

    def _app_tree(self, exes):
        me = os.getpid()
        try:
            kids = {c.pid for c in psutil.Process(me).children(recursive=True)}
        except psutil.Error:
            kids = set()
        return me, {me} | kids

    def show_window(self, show):
        if not self.win:
            raise ProviderError("The Apple Music window isn't ready yet.")
        if show:
            self.win.show()
            HIDDEN_FLAG.unlink(missing_ok=True)
        else:
            self.win.hide()
            HIDDEN_FLAG.write_text("1")

    def state(self):
        st = super().state()
        st.update({"apple_status": self.status, "apple_window": self.win is not None})
        return st
