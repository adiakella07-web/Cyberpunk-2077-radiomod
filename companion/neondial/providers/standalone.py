"""Standalone Spotify mode: no music app has to be running.

Neon Dial runs a small Spotify Connect receiver (librespot) that shows up in Spotify as the device
"Neon Dial FM", like a smart speaker. Its audio goes straight into the game's radio stream, so it plays
through the game's radio mix. Needs Spotify Premium. The first time you pick the device in a Spotify app on the same network it logs itself in
(no browser or password entry here).

Start something on it once from any Spotify app (phone is fine): Devices -> "Neon Dial FM". After that you can
close Spotify. Tuning out of the station stalls librespot's output (so the music holds its place) and tuning
back in continues from there.
"""
import asyncio
import os
import pathlib
import re
import subprocess
import sys
import webbrowser

from ..config import DATA_DIR
from ..log import log
from ..tasks import spawn
from . import Provider

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
URL = re.compile(r"https://accounts\.spotify\.com\S+")
TITLE = re.compile(r"Loading <(.+?)> with Spotify URI")
KEEP = ("authenticated", "logged in", "browse", "oauth", "device", "loading", "error", "warn", "panic", "listening", "country")


def librespot_path():
    env = os.environ.get("NEONDIAL_LIBRESPOT")
    cands = [pathlib.Path(env)] if env else []
    base = pathlib.Path(sys.executable).parent if getattr(sys, "frozen", False) else pathlib.Path(__file__).resolve().parents[2]
    cands += [base / "librespot.exe"]               # only the copy shipped next to this program
    return next((c for c in cands if c.exists()), None)


class StandaloneProvider(Provider):
    name = "standalone"

    def __init__(self, cfg, engine):
        self.engine = engine
        self.device_name = "Neon Dial FM"
        self.exe = librespot_path()
        self.login = (cfg.get("spotify_login") or "zeroconf").lower()   # zeroconf = pick the device in Spotify, no browser
        self.tuned = False
        self.title = ""
        self._wiping = False
        self.status = ("waiting: in the Spotify app (same Wi-Fi) pick the device \"Neon Dial FM\"; the first pick also logs it in"
                       if self.exe else "librespot.exe not found next to NeonDial.exe")
        self.proc = None
        self._task = None
        self._opened = False

    async def start(self):
        self.engine.hold = True          # keep buffered music while nobody is tuned in
        if self.exe:
            self._task = spawn(self._run())

    async def stop(self):
        self.tuned = False
        self.engine.hold = False
        if self._task:
            self._task.cancel()
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.terminate()
            except ProcessLookupError:
                pass

    async def play(self):
        self.tuned = True

    async def pause(self):
        self.tuned = False

    async def _run(self):
        cache = DATA_DIR / "librespot"
        cache.mkdir(parents=True, exist_ok=True)
        while True:
            cmd = [str(self.exe), "--name", self.device_name, "--backend", "pipe", "--format", "S16",
                   "--bitrate", "320", "--cache", str(cache), "--disable-audio-cache",
                   "--initial-volume", "100", "--device-type", "speaker"]
            if (cache / "credentials.json").exists():   # already paired: don't advertise on the network (re-checked every start)
                cmd.append("--disable-discovery")
            if self.login == "oauth":                   # optional: log in through a browser window instead
                cmd.append("--enable-oauth")
            self.proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=NO_WINDOW)
            spawn(self._stderr(self.proc))
            while True:
                # Not tuned in -> don't read: librespot's output blocks, so playback holds its place.
                if not self.tuned or not self.engine.room():
                    await asyncio.sleep(0.02)
                    continue
                data = await self.proc.stdout.read(8192)
                if not data:
                    break
                self.engine.feed(data)
            self.status = "Spotify receiver stopped; restarting"
            log(self.status)
            await asyncio.sleep(3)

    async def _stderr(self, proc):
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            text = line.decode(errors="replace").strip()
            low = text.lower()
            m_title = TITLE.search(text)
            if m_title:
                self.title = m_title.group(1)
            m = URL.search(text) if self.login == "oauth" else None
            if m and not self._opened:
                self._opened = True
                webbrowser.open(m.group(0))
                self.status = "log in to Spotify in the browser window that opened"
            if "authenticated" in low or "logged in" in low:
                self.status = f"ready: in Spotify, pick the device \"{self.device_name}\" and start a playlist"
            if any(k in low for k in KEEP) and not m_title:      # song titles stay out of the log (listening history)
                log("spotify: " + text[:160])

    async def forget(self):
        """Sign out: stop the receiver (it restarts with no saved login and advertises itself again)."""
        self.title = ""
        self.status = "signed out: pick the device \"Neon Dial FM\" in a Spotify app to log in again"
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.terminate()
            except ProcessLookupError:
                pass
        await asyncio.sleep(0.5)

    def state(self):
        return {"standalone_status": self.status, "librespot_found": self.exe is not None,
                "now": {"title": self.title, "artist": "", "playing": self.tuned}}
