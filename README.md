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

## Three modes (switch in the control panel, http://127.0.0.1:8765)
**Music app mode** (default): works with Apple Music or Spotify running on your PC, as described above.

**Standalone Spotify mode**: no music app needs to be open. Neon Dial runs its own Spotify Connect receiver
(librespot) that shows up in Spotify as the device **"Neon Dial FM"**. Needs Spotify Premium.
1. Switch Mode to *Standalone Spotify* in the in-game panel.
2. In any Spotify app on the same Wi-Fi (your phone is fine) choose the device **Neon Dial FM** and start a playlist. The first pick logs it in by itself, with no browser and no password; you can then close Spotify.
3. Tune to the station in-game: the music plays through the game's radio mix; tune away and it holds its place.
**Standalone Apple Music mode**: no Apple Music app needed. Neon Dial hosts the normal Apple Music website (music.apple.com) in a
built-in browser window (Microsoft Edge WebView2, already on Windows 11 and most Windows 10).
1. Switch Mode to *Standalone Apple Music* in the in-game panel. A small window opens (alt-tab to it if you play fullscreen): sign in with your Apple ID once and start a playlist, then click **Hide window**. It stays hidden from then on.
2. Tune to the station: the page plays, its audio is captured from Neon Dial's own browser processes and goes through the game's radio mix. Tune away: it pauses and keeps its place.
No developer account or tokens, it is just you logged in on the website. (Apple's DRM allows playback only in approved players such as its website, so this is the only app-free route.)

## Controls and the in-game panel
No web page needed: open the **Cyber Engine Tweaks overlay** (its usual hotkey, default ~) and use the **Neon Dial** window: switch mode,
prev/next, show the Apple sign-in window (first time only), pick a sound texture, and tune the radio physics. Hotkeys for next/previous
track can be bound in CET's bindings. Everything else is the normal in-game radio: station wheel, radio on/off, volume.
(An optional browser control page exists but is switched off by default, see SECURITY.md.)

## Station look and now-playing
The station has its own icon (a tuner dial in the game's yellow HUD style) and shows the **current song as "Artist - Title"** on the radio select screen and
in the station-switch pop-up like other stations do (Spotify standalone shows the title).

## Privacy and security
See [SECURITY.md](SECURITY.md): logins are never stored by Neon Dial itself, nothing identifying reaches logs or the panel, nothing is uploaded, and there is a one-click
"Sign out and erase saved logins" in the in-game panel. The browser control page is off by default.

## Radio physics and texture
- **Radio boxes**: the *Radioport volume* setting now applies to boxes (RadioExt ignores it), volume falls off with distance
  (full volume within ~4 m, silent beyond ~45 m, adjustable), and it is quieter inside a car. If the car (or pocket radio) already plays Neon Dial FM, the box is muted so the same station never plays twice with an echo.
- **Texture**: *Radio* (band-limited with light hiss and crackle), *Lo-fi*, or *Warm tape*, applied to the stream itself.

## Limits
- Windows 10 (2004+) / 11 only.
- Music app mode: the app must be running with a playlist loaded. Neon Dial finds which process is really playing the
  sound, tests capture strategies and only keeps one that works; otherwise it restores the app's volume and plays through your speakers
  (the control panel shows which path is active, and an Activity log explains why).
- If the companion is killed while you're tuned in, the app's volume stays low until Neon Dial next starts (it restores on launch) or you raise it in the Windows volume mixer.
- librespot is an unofficial Spotify client; using it is a grey area under Spotify's terms.

## Status
Early release. Verified in development: the stream, tune-in/out logic and live-audio path (with a stand-in for the capture helper), and that the Windows binaries build in CI. Not verified on a real PC by me: capture of Apple Music/Spotify and the volume handling (the app logs what it finds), and the two standalone modes. Please report how it behaves in-game via [Issues](../../issues).

## Developing
- `companion/`: Python companion (`python companion/run.py --provider demo` plays a test tone when you tune in; needs Python 3.11+).
- `launcher/`: C++ RED4ext plugin. `vortex_package/`: files shipped in the zip. `tools/make_vortex_zip.py`: packager.
- Releases are built by GitHub Actions: push a tag like `v1.0.0`.

## Credits
[RadioExt](https://github.com/justarandomguyintheinternet/CP77_radioExt) (custom stations), [RED4ext](https://github.com/WopsS/RED4ext) and its SDK (plugin loader), Cyber Engine Tweaks.
Neon Dial is a fan project, not affiliated with CD PROJEKT RED. MIT licensed.
