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


def load(path=None):
    """defaults < optional config.toml < settings.json (written by the web UI)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg = copy.deepcopy(DEFAULTS)
    p = pathlib.Path(path) if path else pathlib.Path("config.toml")
    if p.exists():
        with open(p, "rb") as f:
            _merge(cfg, tomllib.load(f))
    if SETTINGS_FILE.exists():
        try:
            _merge(cfg, json.loads(SETTINGS_FILE.read_text()))
        except Exception:
            pass
    return cfg


def save_settings(patch: dict):
    cur = {}
    if SETTINGS_FILE.exists():
        try:
            cur = json.loads(SETTINGS_FILE.read_text())
        except Exception:
            cur = {}
    _merge(cur, patch)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(cur, indent=2))
