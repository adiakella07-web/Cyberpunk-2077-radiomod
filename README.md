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
- **RadioExt** registers the station and plays a local stream (`http://127.0.0.1:8766/Neon_Dial_Your_Music.mp3`) through the game's own audio engine.
- **NeonDial.dll**, a tiny RED4ext plugin, starts `NeonDial.exe` with the game; the exe quits (and cleans up) when the game exits.
- **NeonDial.exe** notices when you tune in or out of the station (RadioExt opens/closes the stream) and presses play/pause on your music app through Windows' media controls.
- **NeonDialAudio.exe** captures just that app's audio (Windows "process loopback") and feeds it into the stream, so the music plays **through the game's radio mix**: the in-game radio volume, car muffling and station switching all apply.
  While you're tuned in, the app's own Windows mixer volume is turned down so you don't hear it twice (capture happens before that stage).
  Tune away: the app pauses where it is and its volume is restored. Tune back: it resumes.

## Controls
Everything is the normal in-game radio: station wheel/next/previous (switching away pauses, switching back resumes), radio on/off, the radio volume slider. Extra: prev/next track and app choice at http://127.0.0.1:8765.

## Limits
- Windows 10 (2004+) / 11 only. The music app must be running with a playlist loaded.
- If capture ever gets silence while the app is playing, Neon Dial puts the app's volume back and plays through your speakers instead (shown in the control panel; "Audio" setting can force plain speakers).
- If the companion is killed while you're tuned in, the app's volume stays low until you next start Neon Dial (it restores on launch) or raise it in the Windows volume mixer.
- Some apps may refuse capture; Apple Music's Windows app and Spotify are the targets.

## Status
Early release. Verified in development: the stream, tune-in/out logic and live-audio path (with a stand-in for the capture helper), and that the Windows binaries build in CI. Not yet verified on a real PC: process-loopback capture of Apple Music/Spotify and the volume handling. Please report how it behaves in-game via [Issues](../../issues).

## Developing
- `companion/`: Python companion (`python companion/run.py --provider demo` plays a test tone when you tune in; needs Python 3.11+).
- `launcher/`: C++ RED4ext plugin. `vortex_package/`: files shipped in the zip. `tools/make_vortex_zip.py`: packager.
- Releases are built by GitHub Actions: push a tag like `v1.0.0`.

## Credits
[RadioExt](https://github.com/justarandomguyintheinternet/CP77_radioExt) (custom stations), [RED4ext](https://github.com/WopsS/RED4ext) and its SDK (plugin loader), Cyber Engine Tweaks.
Neon Dial is a fan project, not affiliated with CD PROJEKT RED. MIT licensed.
