# Neon Dial

**Your own music, on the Cyberpunk 2077 radio dial.** Neon Dial adds a station, **Neon Dial FM**, as the last
entry in the in-game radio list. Open Apple Music (or Spotify) on your PC, load any playlist, tune to the station and it plays.
Tune away and it pauses. No accounts, API keys or tokens.

## Install (players)
1. Install the prerequisites with Vortex: **Cyber Engine Tweaks**, **RED4ext**, **RadioExt**.
2. Download `NeonDial-vortex.zip` from the [Releases](../../releases) page and add it to Vortex (drag it in, or *Install from file*), then enable and deploy.
3. Open Apple Music/Spotify, start a playlist, launch the game from Vortex, tune to **Neon Dial FM**.

Control panel (prev/next, choose music app): http://127.0.0.1:8765 while the game runs.

## How it works
- **RadioExt** registers the station and plays a local stream, `http://127.0.0.1:8765/stream.mp3` (silent).
- **NeonDial.dll**, a tiny RED4ext plugin, starts `NeonDial.exe` with the game and stops it on exit.
- **NeonDial.exe** notices you tuned in (a listener connected to the stream) and sends play/pause to your music app through
  Windows' built-in media controls, the same ones your keyboard media keys use.

## Limits
- Music plays from the music app through your normal output, **not** through the game's radio mix: no in-game radio volume, no car muffling.
- Windows 10/11 only. The music app must be running with a playlist loaded.

## Status
Early release. Verified in development: the stream and tune-in/out logic, and that the launcher DLL compiles and exports
the entry points RED4ext needs. Please report how it behaves in-game via [Issues](../../issues).

## Developing
- `companion/`: Python companion (`python companion/run.py --provider demo` plays a test tone when you tune in; needs Python 3.11+).
- `launcher/`: C++ RED4ext plugin. `vortex_package/`: files shipped in the zip. `tools/make_vortex_zip.py`: packager.
- Releases are built by GitHub Actions: push a tag like `v1.0.0`.

## Credits
[RadioExt](https://github.com/justarandomguyintheinternet/CP77_radioExt) (custom stations), [RED4ext](https://github.com/WopsS/RED4ext) and its SDK (plugin loader), Cyber Engine Tweaks.
Neon Dial is a fan project, not affiliated with CD PROJEKT RED. MIT licensed.
