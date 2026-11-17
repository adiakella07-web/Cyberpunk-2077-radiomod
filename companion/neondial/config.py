import copy
import json
import pathlib
import tomllib

DATA_DIR = pathlib.Path.home() / ".neondial"
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULTS = {
    "web_panel": False,           # optional browser control page (the in-game panel is the default)
    "port": 8765,                 # control panel (only if web_panel is on)
    "stream_port": 8766,          # audio stream for the game (Icecast-style)
    "provider": "system",         # system | demo
    "music_app": "auto",          # auto | apple | spotify | itunes ...
    "spotify_login": "zeroconf",  # zeroconf (pick the device in Spotify) | oauth (browser window)
    "texture": "off",             # off | radio | lofi | warm
    "output": "game",             # game = through the game radio mix | speakers = plain playback
    "idle_pause_seconds": 1.0,
    "game_process": "Cyberpunk2077.exe",
}


def wipe_credentials():
    """Sign out of everything Neon Dial may have stored: the Spotify receiver's login cache and the embedded browser profile."""
    import shutil
    for d in (DATA_DIR / "librespot", DATA_DIR / "webview"):
        shutil.rmtree(d, ignore_errors=True)
    for f in (DATA_DIR / "apple_window_hidden", DATA_DIR / "volume_state.json"):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        (DATA_DIR / "wipe_on_start").write_text("1")        # the browser profile may still be locked: finish next start
    except OSError:
        pass


def finish_pending_wipe():
    import shutil
    marker = DATA_DIR / "wipe_on_start"
    if marker.exists():
        shutil.rmtree(DATA_DIR / "webview", ignore_errors=True)
        try:
            marker.unlink()
        except OSError:
            pass


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


ALLOWED = {
    "provider": ("system", "standalone", "apple-standalone", "demo"),
    "music_app": ("auto", "apple", "spotify", "itunes"),
    "spotify_login": ("zeroconf", "oauth"),
    "texture": ("off", "radio", "lofi", "warm"),
    "output": ("game", "speakers"),
}


def sanitize(cfg):
    """Settings may come from files other programs can write, so only accept known keys with sane values."""
    clean = copy.deepcopy(DEFAULTS)
    for key, default in DEFAULTS.items():
        val = cfg.get(key, default)
        if key in ALLOWED:
            val = val if val in ALLOWED[key] else default
        elif key in ("port", "stream_port"):
            val = val if isinstance(val, int) and not isinstance(val, bool) and 1024 <= val <= 65535 else default
        elif key == "idle_pause_seconds":
            val = float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) and 0.1 <= val <= 30 else default
        elif key == "web_panel":
            val = val if isinstance(val, bool) else default
        elif key == "game_process":
            val = val if isinstance(val, str) and val.lower().endswith(".exe") and "\\" not in val and "/" not in val else default
        clean[key] = val
    return clean


def load(path=None):
    """defaults < optional config file (only when --config is given: never read from the working directory) < settings.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg = copy.deepcopy(DEFAULTS)
    if path and pathlib.Path(path).exists():
        with open(path, "rb") as f:
            _merge(cfg, tomllib.load(f))
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            if isinstance(data, dict):
                _merge(cfg, data)
        except Exception:
            pass
    return sanitize(cfg)


def save_settings(patch: dict):
    cur = {}
    if SETTINGS_FILE.exists():
        try:
            cur = json.loads(SETTINGS_FILE.read_text())
        except Exception:
            cur = {}
    _merge(cur, patch)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=2))
    tmp.replace(SETTINGS_FILE)                       # atomic: never leave a half-written settings file
