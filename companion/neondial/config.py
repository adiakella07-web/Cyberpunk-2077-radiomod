import copy
import json
import pathlib
import tomllib

DATA_DIR = pathlib.Path.home() / ".neondial"
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULTS = {
    "port": 8765,                 # control panel
    "stream_port": 8766,          # audio stream for the game (Icecast-style)
    "provider": "system",         # system | demo
    "music_app": "auto",          # auto | apple | spotify | itunes ...
    "spotify_login": "zeroconf",  # zeroconf (pick the device in Spotify) | oauth (browser window)
    "texture": "off",             # off | radio | lofi | warm
    "output": "game",             # game = through the game radio mix | speakers = plain playback
    "idle_pause_seconds": 0.4,
    "game_process": "Cyberpunk2077.exe",
}


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
