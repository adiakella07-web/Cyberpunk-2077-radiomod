"""Plays your running music app (Apple Music, Spotify, iTunes) as the in-game station.

Two parts:
  * Control: Windows' built-in media controls (SMTC) press play/pause. No accounts or tokens.
  * Audio:   NeonDialAudio.exe captures just that app's audio (Windows "process loopback") and we stream
             it to the game, so it plays through the game's radio mix. The app's own Windows mixer volume is
             turned down meanwhile so you don't hear it twice (capture happens before that volume stage).
             If capture turns out to be silent, we put the volume back and fall back to plain speakers.
Tune in -> play. Tune out -> pause (resumes where it left off) and the app's volume is restored.
"""
import asyncio
import json
import os
import pathlib
import subprocess
import sys
import time

import psutil

from ..config import DATA_DIR
from . import Provider, ProviderError

try:  # Windows only
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
    )
    AVAILABLE = True
except Exception:  # pragma: no cover
    AVAILABLE = False

PREFERRED = ("applemusic", "apple", "itunes", "spotify", "music")
EXES = (("applemusic", ["applemusic.exe"]), ("itunes", ["itunes.exe"]), ("apple", ["applemusic.exe", "itunes.exe"]),
        ("spotify", ["spotify.exe"]))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
STATE_FILE = DATA_DIR / "volume_state.json"


def helper_path():
    env = os.environ.get("NEONDIAL_AUDIO_HELPER")
    cands = [pathlib.Path(env)] if env else []
    base = pathlib.Path(sys.executable).parent if getattr(sys, "frozen", False) else pathlib.Path(__file__).resolve().parents[2]
    cands += [base / "NeonDialAudio.exe", pathlib.Path.cwd() / "NeonDialAudio.exe"]
    return next((c for c in cands if c.exists()), None)


def exes_for(aumid: str):
    a = aumid.lower()
    if a.endswith(".exe"):
        return [a.rsplit("\\", 1)[-1]]
    for key, exes in EXES:
        if key in a:
            return exes
    return []


def app_pids(exe_names):
    """-> (root pid, every pid of the app incl. children)"""
    procs = []
    for p in psutil.process_iter(["name", "pid", "ppid"]):
        if (p.info["name"] or "").lower() in exe_names:
            procs.append(p)
    pids = {p.pid for p in procs}
    roots = [p for p in procs if p.info["ppid"] not in pids]
    root = roots[0] if roots else None
    allp = set(pids)
    if root:
        try:
            allp |= {c.pid for c in root.children(recursive=True)}
        except psutil.Error:
            pass
    return (root.pid if root else None), allp


class Capture:
    def __init__(self, engine, helper):
        self.engine, self.helper = engine, helper
        self.proc = None
        self.pid = None
        self.task = None
        self.last_audio = 0.0
        self.started = 0.0

    @property
    def running(self):
        return self.proc is not None and self.proc.returncode is None

    async def start(self, pid):
        await self.stop()
        self.proc = await asyncio.create_subprocess_exec(
            str(self.helper), "capture", str(pid),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=NO_WINDOW)
        self.pid, self.started, self.last_audio = pid, time.monotonic(), 0.0
        self.task = asyncio.create_task(self._read(self.proc))

    async def _read(self, proc):
        while True:
            data = await proc.stdout.read(8192)
            if not data:
                break
            if data.count(0) != len(data):
                self.last_audio = time.monotonic()
            self.engine.feed_live(data)
        err = (await proc.stderr.read()).decode(errors="replace").strip()
        if err:
            print("[capture]", err)

    async def stop(self):
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.terminate()
            except ProcessLookupError:
                pass
        if self.task:
            self.task.cancel()
        self.proc = self.task = None


class SystemProvider(Provider):
    name = "system"

    def __init__(self, cfg, engine):
        self.engine = engine
        self.pref = (cfg.get("music_app") or "auto").lower()
        self.output = cfg.get("output", "game")          # game | speakers
        self.helper = helper_path()
        self.capture = Capture(engine, self.helper) if self.helper else None
        self.mgr = None
        self.tuned = False
        self.we_started = False
        self.fallback = None                              # reason string if we fell back to speakers
        self.orig = None                                  # app volume before we lowered it
        self.vol_pids = set()
        self.now, self.apps, self.error = {}, [], None
        self._monitor = None

    # ---- media session -------------------------------------------------
    async def _manager(self):
        if not AVAILABLE:
            raise ProviderError("Windows media controls are unavailable (needs Windows 10/11).")
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

    # ---- helper calls --------------------------------------------------
    async def _volume(self, vol, pids):
        if not self.helper or not pids:
            return {}
        proc = await asyncio.create_subprocess_exec(
            str(self.helper), "volume", f"{vol:.3f}", *map(str, sorted(pids)),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, creationflags=NO_WINDOW)
        out, _ = await proc.communicate()
        res = {}
        for line in out.decode(errors="replace").splitlines():
            try:
                pid, prev = line.split()
                res[int(pid)] = float(prev)
            except ValueError:
                pass
        return res

    async def _duck(self, pids):
        prev = await self._volume(0.0, pids)
        if prev:
            if self.orig is None:
                best = max(prev.values())
                self.orig = best if best > 0.05 else 1.0     # 0 = leftover from a crash -> assume full
            self.vol_pids |= set(prev)
            STATE_FILE.write_text(json.dumps({"orig": self.orig, "pids": sorted(self.vol_pids)}))
        return bool(prev)

    async def _restore(self):
        if self.orig is not None:
            pids = set(self.vol_pids)
            try:
                pids |= app_pids(exes_for((self.now or {}).get("app", "")))[1]
            except Exception:
                pass
            await self._volume(self.orig, pids)
        self.orig, self.vol_pids = None, set()
        try:
            STATE_FILE.unlink()
        except FileNotFoundError:
            pass

    async def recover(self):
        """If we crashed while the app was turned down, put it back."""
        try:
            st = json.loads(STATE_FILE.read_text())
        except Exception:
            return
        await self._volume(float(st.get("orig", 1.0)), set(st.get("pids", [])))
        STATE_FILE.unlink(missing_ok=True)

    # ---- Provider API --------------------------------------------------
    async def start(self):
        await self.recover()

    async def stop(self):
        self.tuned = False
        if self._monitor:
            self._monitor.cancel()
        await self._restore()
        if self.capture:
            await self.capture.stop()

    def _game_mix(self):
        return self.output == "game" and self.capture is not None and not self.fallback

    async def play(self):
        s = await self._session()
        self.tuned = True
        pids = set()
        if self._game_mix():
            root, pids = app_pids(exes_for(s.source_app_user_model_id))
            if root:
                if not self.capture.running or self.capture.pid != root:
                    await self.capture.start(root)
                self.engine.flush()
                await self._duck(pids)
            else:
                pids = set()
        if s.get_playback_info().playback_status != Status.PLAYING:
            await s.try_play_async()
            self.we_started = True
        if pids:
            if self._monitor:
                self._monitor.cancel()
            self._monitor = asyncio.create_task(self._after_play(pids))

    async def _after_play(self, pids):
        t0 = time.monotonic()
        # the app's mixer session may only appear once audio starts: keep turning it down briefly
        while self.tuned and time.monotonic() - t0 < 4:
            await self._duck(pids)
            await asyncio.sleep(0.25)
        # self-check: audio must actually arrive through capture, otherwise fall back to speakers
        while self.tuned:
            await asyncio.sleep(1)
            try:
                s = await self._session()
                playing = s.get_playback_info().playback_status == Status.PLAYING
            except Exception:
                continue
            silent_for = time.monotonic() - max(self.capture.last_audio, t0 + 2)
            if playing and silent_for > 6:
                self.fallback = "Couldn't capture the music app's audio; playing through your speakers instead."
                print("[system]", self.fallback)
                await self._restore()
                await self.capture.stop()
                return

    async def pause(self):
        self.tuned = False
        if self._monitor:
            self._monitor.cancel()
        try:
            s = await self._session()
            if self.we_started and s.get_playback_info().playback_status == Status.PLAYING:
                await s.try_pause_async()
        except ProviderError:
            pass
        finally:
            self.we_started = False
            await asyncio.sleep(0.3)       # let the pause land before the volume comes back
            await self._restore()

    async def next(self):
        await (await self._session()).try_skip_next_async()

    async def prev(self):
        await (await self._session()).try_skip_previous_async()

    async def set_output(self, mode):
        self.output = mode
        self.fallback = None
        if mode == "speakers":
            await self._restore()
            if self.capture:
                await self.capture.stop()

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
        return {"now": self.now, "apps": self.apps, "music_app": self.pref, "provider_error": self.error,
                "output": self.output, "helper_found": self.helper is not None,
                "capturing": bool(self.capture and self.capture.running and self._game_mix()),
                "fallback": self.fallback}
