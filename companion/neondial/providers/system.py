"""Controls the music app that is already running (Apple Music, Spotify, iTunes, ...) through
Windows' built-in media controls (the same thing your keyboard media keys / volume flyout use).
No accounts, tokens or API keys. Whatever playlist you have loaded in the app is what plays.

Tune in to the station -> play.   Tune out -> pause.
"""
import time

from . import Provider, ProviderError

try:  # Windows only
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
    )
    AVAILABLE = True
except Exception:  # pragma: no cover - non-Windows
    AVAILABLE = False

PREFERRED = ("applemusic", "apple", "itunes", "spotify", "music")


class SystemProvider(Provider):
    name = "system"

    def __init__(self, cfg, engine):
        self.pref = (cfg.get("music_app") or "auto").lower()
        self.mgr = None
        self.we_started = False
        self.now = {}
        self.apps = []
        self.error = None

    async def _manager(self):
        if not AVAILABLE:
            raise ProviderError("Windows media controls are unavailable (this only works on Windows 10/11).")
        if self.mgr is None:
            self.mgr = await Manager.request_async()
        return self.mgr

    async def _session(self):
        mgr = await self._manager()
        sessions = list(mgr.get_sessions())
        self.apps = [s.source_app_user_model_id for s in sessions]
        if not sessions:
            raise ProviderError("No music app found. Open Apple Music or Spotify and start a playlist once.")
        if self.pref != "auto":
            for s in sessions:
                if self.pref in s.source_app_user_model_id.lower():
                    return s
            raise ProviderError(f"'{self.pref}' isn't running.")
        for key in PREFERRED:
            for s in sessions:
                if key in s.source_app_user_model_id.lower():
                    return s
        return mgr.get_current_session() or sessions[0]

    async def play(self):
        s = await self._session()
        if s.get_playback_info().playback_status != Status.PLAYING:
            await s.try_play_async()
            self.we_started = True

    async def pause(self):
        try:
            s = await self._session()
            if self.we_started and s.get_playback_info().playback_status == Status.PLAYING:
                await s.try_pause_async()
        finally:
            self.we_started = False

    async def next(self):
        await (await self._session()).try_skip_next_async()

    async def prev(self):
        await (await self._session()).try_skip_previous_async()

    async def refresh(self):
        try:
            s = await self._session()
            p = await s.try_get_media_properties_async()
            self.now = {"title": p.title if p else "", "artist": p.artist if p else "",
                        "playing": s.get_playback_info().playback_status == Status.PLAYING,
                        "app": s.source_app_user_model_id}
            self.error = None
        except ProviderError as e:
            self.now, self.error = {}, str(e)
        except Exception as e:
            self.now, self.error = {}, f"{type(e).__name__}: {e}"

    def state(self):
        return {"now": self.now, "apps": self.apps, "music_app": self.pref, "provider_error": self.error}
