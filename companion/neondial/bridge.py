"""In-game control panel bridge: the CET addon (NeonDial/init.lua) and this program exchange small text files,
so everything can be done from the in-game overlay, no web page needed."""
import asyncio
import os
import pathlib
import sys
import time

from .log import recent, redact


def find_mod_dir():
    env = os.environ.get("NEONDIAL_MODDIR")
    if env:
        return pathlib.Path(env)
    if getattr(sys, "frozen", False):
        exe_dir = pathlib.Path(sys.executable).parent            # <game>/red4ext/plugins/NeonDial
        root = exe_dir.parent.parent.parent
        d = root / "bin" / "x64" / "plugins" / "cyber_engine_tweaks" / "mods" / "NeonDial"
        if d.exists():
            return d
    return None


def _clean(s):
    return ("" if s is None else str(s)).replace("\r", " ").replace("\n", " ")


def status_text(hub, engine):
    p = hub.provider
    st = p.state()
    now = st.get("now") or {}
    if p.name == "system" or p.name == "apple-standalone":
        if st.get("fallback"):
            path = "speakers (fallback)"
        elif st.get("capturing"):
            path = "game radio mix"
        else:
            path = "starts when you tune in"
        note = st.get("fallback") or st.get("provider_error") or st.get("apple_status") or ""
        if st.get("fallback") and p.name == "system":
            note += "  Tip: for Apple Music in the game's mix use the Standalone Apple Music mode."
    elif p.name == "standalone":
        path = "game radio mix (Spotify receiver)"
        note = st.get("standalone_status", "")
    else:
        path, note = "test tone", ""
    lines = {
        "ts": int(time.time()), "mode": p.name, "tuned": int(bool(hub.tuned)), "listeners": hub.listeners,
        "path": path, "note": redact(note or hub.error or ""), "title": now.get("title", ""), "artist": now.get("artist", ""),
        "playing": int(bool(now.get("playing"))), "texture": engine.texture.mode,
    }
    out = [f"{k}={_clean(v)}" for k, v in lines.items()]
    out += [f"log={_clean(l)}" for l in recent(10)]
    return "\n".join(out) + "\n"


async def run(app, engine, mod_dir):
    hub = app["hub"]
    status_f, cmd_f = mod_dir / "status.txt", mod_dir / "command.txt"
    last_write = 0.0
    while True:
        try:
            if cmd_f.exists():
                text = cmd_f.read_text(errors="replace")[:2000]          # the file is tiny; ignore anything bigger
                cmd_f.unlink(missing_ok=True)
                for line in text.splitlines()[:10]:
                    if "=" in line:
                        k, v = line.split("=", 1)
                        await app["do"](k.strip(), v.strip())
            if time.monotonic() - last_write > 1.0:
                if hasattr(hub.provider, "refresh"):
                    await hub.provider.refresh()
                tmp = mod_dir / "status.tmp"
                tmp.write_text(status_text(hub, engine), encoding="utf-8")
                os.replace(tmp, status_f)
                last_write = time.monotonic()
        except Exception as e:                                   # never let the bridge die
            from .log import log
            log(f"bridge: {type(e).__name__}: {e}")
        await asyncio.sleep(0.25)
