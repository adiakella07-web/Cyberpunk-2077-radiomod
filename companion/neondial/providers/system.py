"""Plays your running music app (Apple Music, Spotify, iTunes) as the in-game station.

  * Control: Windows' built-in media controls (SMTC) press play/pause. No accounts or tokens.
  * Audio:   NeonDialAudio.exe captures that app's audio (Windows "process loopback"); we stream it to the
             game so it plays through the game's radio mix (radio volume, muffling, station switching).
             The app's own mixer volume is turned down meanwhile so you don't hear it twice.

Nothing is assumed: after pressing play we find the process that is really making sound, try capture
strategies in turn, and only keep one that is verified to deliver audio. If none works (or turning the app
down silences the capture) we put the volume back and play through the speakers.
"""
import array
import asyncio
import collections
import json
import os
import pathlib
import subprocess
import sys
import time

import numpy as np
import psutil

from ..config import DATA_DIR
from ..log import log
from ..tasks import spawn
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
EXES = (("applemusic", ["applemusic.exe"]), ("itunes", ["itunes.exe"]),
        ("apple", ["applemusic.exe", "itunes.exe"]), ("spotify", ["spotify.exe"]))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
STATE_FILE = DATA_DIR / "volume_state.json"
PROFILE_FILE = DATA_DIR / "capture_profile.json"   # what this PC does with an app's volume when capturing (learned once)
FLOOR = 0.04                                        # the app's own volume while it is being captured (-28 dB)
AUDIBLE = 0.01          # session meter level (0-1) that counts as 'the app is making sound'
REAL = 150              # capture level (of 32767) that counts as real audio; level 1-2 is just Windows' dither noise


def helper_path():
    env = os.environ.get("NEONDIAL_AUDIO_HELPER")
    cands = [pathlib.Path(env)] if env else []
    base = pathlib.Path(sys.executable).parent if getattr(sys, "frozen", False) else pathlib.Path(__file__).resolve().parents[2]
    cands += [base / "NeonDialAudio.exe"]          # only the copy shipped next to this program
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
    procs = [p for p in psutil.process_iter(["name", "pid", "ppid"]) if (p.info["name"] or "").lower() in exe_names]
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


def related(pid, app_all, exes):
    if pid in app_all:
        return True
    try:
        p = psutil.Process(pid)
        if (p.name() or "").lower() in exes:
            return True
        return bool({a.pid for a in p.parents()} & app_all)
    except psutil.Error:
        return False


def find_game_pid(name="Cyberpunk2077.exe"):
    for p in psutil.process_iter(["name", "pid"]):
        if (p.info["name"] or "").lower() == name.lower():
            return p.pid
    return None


class Capture:
    def __init__(self, engine, helper):
        self.engine, self.helper = engine, helper
        self.proc = self.task = None
        self.key = None
        self.last_audio = 0.0
        self.max_peak = 0
        self.gain = 1.0
        self.real_chunks = 0
        self._rem = b""
        self._peaks = collections.deque(maxlen=600)

    def recent_peak(self, seconds):
        cutoff = time.monotonic() - seconds
        return max((p for t, p in self._peaks if t >= cutoff), default=0)

    @property
    def running(self):
        return self.proc is not None and self.proc.returncode is None

    async def start(self, pid, mode="include"):
        await self.stop()
        self.proc = await asyncio.create_subprocess_exec(
            str(self.helper), "capture", str(pid), mode, "--parent", str(os.getpid()),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=NO_WINDOW)
        self.key, self.last_audio, self.max_peak = (pid, mode), 0.0, 0
        self.real_chunks = 0
        self._rem, self._peaks = b"", collections.deque(maxlen=600)
        self.task = spawn(self._read(self.proc))

    async def _read(self, proc):
        while True:
            data = await proc.stdout.read(8192)
            if not data:
                break
            data = self._rem + data
            n = len(data) // 4 * 4
            data, self._rem = data[:n], data[n:]
            if not n:
                continue
            if data.count(0) != n:
                a = np.frombuffer(data, dtype="<i2")
                peak = int(max(a.max(), -int(a.min())))
                now = time.monotonic()
                self._peaks.append((now, peak))
                self.max_peak = max(self.max_peak, peak)
                if peak >= REAL:                       # tiny values are dither noise, not music
                    self.last_audio = now
                    self.real_chunks += 1
                if self.gain != 1.0:
                    data = np.clip(a.astype(np.float32) * self.gain, -32768, 32767).astype("<i2").tobytes()
            self.engine.feed_live(data)
        err = (await proc.stderr.read()).decode(errors="replace").strip()
        if err:
            log(f"capture helper: {err}")

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
        self.game_process = cfg.get("game_process", "Cyberpunk2077.exe")
        self.game_pid = cfg.get("game_pid")
        self.pref = (cfg.get("music_app") or "auto").lower()
        self.output = cfg.get("output", "game")          # game | speakers
        self.helper = helper_path()
        self.capture = Capture(engine, self.helper) if self.helper else None
        self.mgr = None
        self.tuned = False
        self.we_started = False
        self.fallback = None
        self.fail_streak = 0
        self.good = None                                  # label of the capture strategy that worked last
        self.duck_vol = 0.0                               # how far the app's own volume is turned down (learned)
        self.learned = False
        self.post_volume = self._load_profile()           # True: Windows applies the app volume BEFORE capture; None: unknown
        self.strategy = None
        self.orig = None
        self.vol_pids = set()
        self.now, self.apps, self.error = {}, [], None
        self._monitor = None
        self._watch = None

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

    # ---- control hooks (SMTC by default; subclasses replace them) -----------
    prefer_root = False

    async def _ctl_info(self):
        s = await self._session()
        return s.source_app_user_model_id, s.get_playback_info().playback_status == Status.PLAYING

    async def _ctl_play(self):
        return await (await self._session()).try_play_async()

    async def _ctl_pause(self):
        await (await self._session()).try_pause_async()

    async def _ctl_next(self):
        await (await self._session()).try_skip_next_async()

    async def _ctl_prev(self):
        await (await self._session()).try_skip_previous_async()

    async def _ctl_now(self):
        s = await self._session()
        p = await s.try_get_media_properties_async()
        return {"title": p.title if p else "", "artist": p.artist if p else "",
                "playing": s.get_playback_info().playback_status == Status.PLAYING,
                "app": s.source_app_user_model_id}

    def _app_tree(self, exes):
        return app_pids(exes)

    # ---- learned behaviour of this PC ----------------------------------------
    @staticmethod
    def _load_profile():
        try:
            v = json.loads(PROFILE_FILE.read_text()).get("post_volume")
            return v if isinstance(v, bool) else None
        except Exception:
            return None

    def _save_profile(self):
        try:
            PROFILE_FILE.write_text(json.dumps({"post_volume": self.post_volume}))
        except OSError:
            pass

    # ---- helper calls --------------------------------------------------
    async def _run(self, *args):
        if not self.helper:
            return ""
        proc = await asyncio.create_subprocess_exec(
            str(self.helper), *map(str, args),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, creationflags=NO_WINDOW)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), 8)
        except asyncio.TimeoutError:
            proc.kill()
            log("audio helper timed out")
            return ""
        return out.decode(errors="replace")

    async def _sessions(self):
        res = []
        for line in (await self._run("sessions")).splitlines():
            try:
                pid, state, peak = line.split()
                res.append((int(pid), int(state), float(peak)))
            except ValueError:
                pass
        return res

    async def _volume(self, vol, pids):
        if not pids:
            return {}
        res = {}
        for line in (await self._run("volume", f"{vol:.3f}", *sorted(pids))).splitlines():
            try:
                pid, prev = line.split()
                res[int(pid)] = float(prev)
            except ValueError:
                pass
        return res

    async def _duck(self, pids, vol=None):
        prev = await self._volume(self.duck_vol if vol is None else vol, pids)
        if prev:
            if self.orig is None:
                best = max(prev.values())
                self.orig = best if best > 0.05 else 1.0
                log(f"turned the music app's own volume down (was {self.orig:.2f})")
            self.vol_pids |= set(prev)
            self._save_state()
        return bool(prev)

    def _save_state(self):
        procs = []
        for pid in sorted(self.vol_pids):
            try:
                p = psutil.Process(pid)
                procs.append({"pid": pid, "name": p.name(), "created": p.create_time()})
            except psutil.Error:
                pass
        STATE_FILE.write_text(json.dumps({"orig": self.orig, "procs": procs}))

    async def _restore(self):
        if self.orig is not None:
            got = await self._volume(self.orig, set(self.vol_pids))
            log(f"restored the music app's volume ({len(got)} session(s))")
            if not got:
                got = await self._volume(self.orig, set(self.vol_pids) | set(app_pids(exes_for((self.now or {}).get("app", "")))[1]))
        self.orig, self.vol_pids = None, set()
        try:
            STATE_FILE.unlink()
        except FileNotFoundError:
            pass

    async def recover(self):
        """If the last run died while the music app was turned down, put it back. Process ids are reused by Windows, so
        only touch a process that is still the very same one (same name and start time)."""
        try:
            st = json.loads(STATE_FILE.read_text())
            orig = float(st.get("orig", 1.0))
            safe = set()
            for rec in st.get("procs", []):
                try:
                    p = psutil.Process(int(rec["pid"]))
                    if p.name() == rec["name"] and abs(p.create_time() - float(rec["created"])) < 1.5:
                        safe.add(p.pid)
                except (psutil.Error, KeyError, ValueError, TypeError):
                    pass
            if safe and 0.0 <= orig <= 1.0:
                await self._volume(orig, safe)
        except Exception:
            pass
        STATE_FILE.unlink(missing_ok=True)

    # ---- Provider API --------------------------------------------------
    async def start(self):
        await self.recover()

    async def stop(self):
        was_tuned = self.tuned
        self.tuned = False
        for t in (self._monitor, self._watch):
            if t:
                t.cancel()
        if was_tuned:
            try:                                           # leaving the station (or closing the game): stop the music too
                if (await self._ctl_info())[1]:
                    await self._ctl_pause()
            except Exception:
                pass
        await self._restore()
        if self.capture:
            await self.capture.stop()

    def _game_mix(self):
        return self.output == "game" and self.capture is not None and self.fail_streak < 2

    async def play(self):
        aumid, playing = await self._ctl_info()
        self.tuned = True
        self.fallback = None
        exes = exes_for(aumid)
        log(f"music app: {aumid}; output mode: {self.output}; helper: {'found' if self.helper else 'MISSING'}")
        game_mix = self._game_mix()
        if game_mix:
            self.engine.flush()
        if not playing:
            ok = await self._ctl_play()
            log(f"sent play to the music app (accepted={ok})")
            self.we_started = True
        else:
            log("music app was already playing")
        if self._monitor:
            self._monitor.cancel()
        if self._watch:
            self._watch.cancel()
        if game_mix:
            self._monitor = spawn(self._probe_guarded(exes))
        self._watch = spawn(self._keepalive())

    async def _candidates(self, exes):
        root, app_all = self._app_tree(exes)
        me, game = os.getpid(), self.game_pid or find_game_pid(self.game_process)
        sess = await self._sessions()
        skip = {0, me, game}
        mine = sorted(p for p, _, _ in sess if p not in skip and related(p, app_all, exes))
        audible_mine = any(pk > AUDIBLE for p, _, pk in sess if p in mine)
        audible_any = any(pk > AUDIBLE for p, _, pk in sess if p not in skip)
        cands = [("app audio session", p, "include") for p in mine]
        if root and root not in mine:
            cands.append(("app main process", root, "include"))
        cands += [("active audio session", p, "include") for p, _, pk in sess if pk > AUDIBLE and p not in skip and p not in mine]
        if game:
            cands.append(("everything except the game", game, "exclude"))
        if self.prefer_root and root:
            cands.sort(key=lambda c: c[1] != root)
        if self.good:                                     # try what worked before first
            cands.sort(key=lambda c: c[0] != self.good)
        return cands, app_all | set(mine), audible_mine, audible_any

    async def _probe_guarded(self, exes):
        try:
            await self._probe(exes)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log(f"capture setup failed: {type(e).__name__}: {e}")
            await self._give_up("Couldn't set up the game audio path; playing through your speakers.")

    async def _keepalive(self):
        """While tuned in the music should be playing. If it stops by itself (a hiccup in the app or page), start it again."""
        resumes = []
        while self.tuned:
            await asyncio.sleep(2.5)
            try:
                playing = (await self._ctl_info())[1]
            except Exception:
                continue
            if self.tuned and not playing:
                now = time.monotonic()
                resumes = [t for t in resumes if now - t < 30]
                if len(resumes) < 3:                       # never fight the user: give up after 3 tries in 30 s
                    resumes.append(now)
                    log("the music stopped by itself; resuming")
                    try:
                        await self._ctl_play()
                    except Exception:
                        pass

    async def _probe(self, exes):
        """Find a capture strategy that really delivers audio, then silence the app's speakers."""
        t0 = time.monotonic()
        tried, cur, cur_start, audible_since = set(), None, 0.0, None
        success = None
        while self.tuned and time.monotonic() - t0 < 40:
            cands, duck_pids, aud_mine, aud_any = await self._candidates(exes)
            if cur is None:
                nxt = next((c for c in cands if (c[1], c[2]) not in tried), None)
                if nxt is None:
                    if aud_any and time.monotonic() - t0 > 6:
                        break                              # exhausted every strategy
                    await asyncio.sleep(0.5)
                    continue
                cur = nxt
                tried.add((cur[1], cur[2]))
                await self.capture.start(cur[1], cur[2])
                cur_start, audible_since = time.monotonic(), None
                log(f"trying capture: {cur[0]} (pid {cur[1]}, {cur[2]})")
            if self.capture.last_audio > cur_start and self.capture.real_chunks >= 5:
                success = (cur, duck_pids)
                break
            if not self.capture.running:
                log(f"capture '{cur[0]}' stopped unexpectedly")
                cur = None
                continue
            if aud_mine or aud_any:
                audible_since = audible_since or time.monotonic()
                if time.monotonic() - audible_since > 2.5:
                    log(f"capture '{cur[0]}' heard nothing real (loudest level {self.capture.max_peak}) although the app is making sound")
                    cur = None
                    continue
            await asyncio.sleep(0.25)
        if not self.tuned:
            return
        if not success:
            await self._give_up("Couldn't capture the music app's audio (or it never started); playing through your speakers.")
            return
        cur, duck_pids = success
        pre_peak = self.capture.recent_peak(1.5)
        log(f"capture works via '{cur[0]}' (level {pre_peak})")
        if not await self._settle(duck_pids, pre_peak):
            return
        self.good, self.strategy, self.fail_streak, self.learned = cur[0], cur[0], 0, True
        log("game radio mix active" + (f" (boost x{self.capture.gain:.0f})" if self.capture.gain != 1.0 else ""))
        t_ok, last_real = time.monotonic(), time.monotonic()
        while self.tuned:                                  # keep it ducked / capture alive
            await asyncio.sleep(2.5)
            if not self.capture.running:
                await self.capture.start(cur[1], cur[2])
            cands, duck_pids, _, _ = await self._candidates(exes)
            await self._duck(duck_pids)
            if self.capture.recent_peak(1.0) >= 20:
                last_real = time.monotonic()
            elif time.monotonic() - last_real > 12 and time.monotonic() - t_ok > 12:
                try:
                    playing = (await self._ctl_info())[1]
                except Exception:
                    playing = False
                if playing:                                # music is playing but nothing reaches the game: never leave it silent
                    await self._give_up("No audio reached the game for 12 s while the music was playing; using your speakers.")
                    return

    async def _settle(self, duck_pids, pre_peak):
        """Silence the app's own speakers without silencing the capture.

        Depending on the PC, Windows applies an app's volume either AFTER capture (turning the app down also turns the
        capture down) or BEFORE it. We learn which once and remember it, so there is no audible 'test dip' in later runs:
          * volume applied after capture -> keep the app at a low floor and boost the capture back by the same factor
          * volume applied before capture -> turn the app fully off, the capture is unaffected
        """
        known = self.post_volume
        self.capture.gain = (1.0 / FLOOR) if known else 1.0      # pre-set so a known-boost PC never dips
        found = False
        for _ in range(6):                                        # the app's mixer session may appear a moment late
            if await self._duck(duck_pids, FLOOR if known is not False else 0.0):
                found = True
                break
            await asyncio.sleep(0.5)
        if not found:
            await self._give_up("Couldn't find the music app's volume control, so it would play twice; using your speakers.")
            return False
        orig = max(self.orig or 1.0, 0.05)

        if known is True:
            self.capture.gain = min(40.0, orig / FLOOR)
            await asyncio.sleep(1.0)
            raw = self.capture.recent_peak(1.0)
            if raw >= max(20, 0.3 * pre_peak * FLOOR / orig):
                self.duck_vol = FLOOR
                return True
            log(f"remembered setting no longer fits (level {raw}); testing again")
            self.post_volume, known = None, None
        elif known is False:
            await asyncio.sleep(0.8)
            raw = self.capture.recent_peak(0.8)
            if raw >= max(REAL, 0.25 * pre_peak):
                self.duck_vol = 0.0
                return True
            log(f"remembered setting no longer fits (level {raw}); testing again")
            self.post_volume, known = None, None

        # unknown PC: one short test at the low floor (about a quarter of a second), then decide
        self.capture.gain = 1.0
        await self._duck(duck_pids, FLOOR)
        await asyncio.sleep(0.45)
        raw = self.capture.recent_peak(0.3)
        if raw >= 0.5 * max(pre_peak, 1):                         # unaffected by the app's volume
            self.post_volume = False
            await self._duck(duck_pids, 0.0)
            await asyncio.sleep(0.8)
            if self.capture.recent_peak(0.6) >= max(REAL, 0.25 * pre_peak):
                self.duck_vol = 0.0
                log("Windows captures this app before its volume setting: app turned fully down")
            else:
                await self._duck(duck_pids, FLOOR)
                self.duck_vol = FLOOR
            self._save_profile()
            return True
        self.post_volume = True                                   # capture follows the app volume: keep the floor and boost
        self.capture.gain = min(40.0, orig / FLOOR)
        await asyncio.sleep(0.9)
        raw = self.capture.recent_peak(0.8)
        if raw >= max(20, 0.3 * pre_peak * FLOOR / orig):
            self.duck_vol = FLOOR
            self._save_profile()
            log(f"Windows applies this app's volume before capture: keeping it at {int(FLOOR * 100)}% and boosting x{self.capture.gain:.0f}")
            return True
        self.post_volume = None
        await self._give_up("Turning the music app down also silences the capture, so it would play twice; using your speakers.")
        return False

    async def _dump_sessions(self):
        try:
            rows = []
            for pid, _, pk in (await self._sessions())[:8]:
                try:
                    name = psutil.Process(pid).name()
                except psutil.Error:
                    name = "?"
                rows.append(f"{name}#{pid} {pk:.2f}")
            log("audio sessions: " + "; ".join(rows))
        except Exception:
            pass

    async def _give_up(self, why):
        await self._dump_sessions()
        self.fallback = why
        self.fail_streak += 1
        log(why)
        await self._restore()
        if self.capture:
            await self.capture.stop()
        self.engine.flush()

    async def pause(self):
        self.tuned = False
        for t in (self._monitor, self._watch):
            if t:
                t.cancel()
        try:
            if (await self._ctl_info())[1]:                 # whoever started it, leaving the station pauses it
                await self._ctl_pause()
                log("sent pause to the music app")
        except ProviderError:
            pass
        finally:
            self.we_started = False
            await asyncio.sleep(0.3)
            await self._restore()

    async def next(self):
        await self._ctl_next()

    async def prev(self):
        await self._ctl_prev()

    async def set_output(self, mode):
        self.output = mode
        self.fallback, self.fail_streak = None, 0
        if mode == "speakers":
            await self._restore()
            if self.capture:
                await self.capture.stop()

    async def refresh(self):
        try:
            self.now = await self._ctl_now()
            self.error = None
        except ProviderError as e:
            self.now, self.error = {}, str(e)
        except Exception as e:
            self.now, self.error = {}, f"{type(e).__name__}: {e}"

    def state(self):
        return {"now": self.now, "apps": self.apps, "music_app": self.pref, "provider_error": self.error,
                "output": self.output, "helper_found": self.helper is not None,
                "capturing": bool(self.capture and self.capture.running and self.orig is not None),
                "strategy": self.strategy, "fallback": self.fallback}
