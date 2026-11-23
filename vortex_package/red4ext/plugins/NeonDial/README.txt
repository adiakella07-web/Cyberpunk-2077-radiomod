NEON DIAL - your music as an in-game radio station (Cyberpunk 2077)
====================================================================
Version: see the file name of the zip you installed.   Source code: https://github.com/adiakella07-web/Cyberpunk-2077-radiomod (MIT licence)

AI DISCLOSURE
The code, build scripts and documentation of this mod were written by an AI assistant (Claude, by Anthropic) under the author's direction;
the author tested it in the game and directed the fixes. The station icon is drawn by a script (no image-generation model, no third-party art).

REQUIRES (install these first, they are separate mods)
  - Cyber Engine Tweaks (CET)        - RED4ext        - RadioExt
  - Windows 10 (2004+) or 11.  "Standalone Apple Music" also needs the Microsoft Edge WebView2 Runtime (already on Windows 11 / most Windows 10).

HOW TO USE
  Start the game, tune to the last station "Neon Dial FM". Open the CET overlay and use the "Neon Dial" window to choose the mode:
    - Music app: uses Apple Music / Spotify already open on your PC.
    - Standalone Apple Music: a small built-in window shows the Apple Music website; sign in once, start a playlist, click "Hide window".
    - Standalone Spotify: needs the OPTIONAL add-on file (NeonDial-SpotifyAddon-<version>.zip) and Spotify Premium.

WHAT EACH FILE DOES (everything is listed with origin and licence in MANIFEST.md)
  bin/.../cyber_engine_tweaks/mods/NeonDial/init.lua          CET addon: the in-game "Neon Dial" window, radio-box volume/distance fixes, song title on the radio screen.
  bin/.../cyber_engine_tweaks/mods/radioExt/radios/NeonDial/metadata.json   Tells RadioExt about the station (name, local stream address, icon).
  archive/pc/mod/NeonDial.archive                              The station icon (original artwork: a texture + an icon atlas). No base-game assets.
  red4ext/plugins/NeonDial/NeonDial.dll                        RED4ext plugin. Its only job: start NeonDial.exe with the game.
  red4ext/plugins/NeonDial/NeonDial.exe (+ _internal folder)   The companion program: serves the audio to the game on 127.0.0.1 and controls your music app.
  red4ext/plugins/NeonDial/NeonDialAudio.exe                   Small helper: captures one app's audio (Windows "process loopback") and sets that app's mixer volume.
  red4ext/plugins/NeonDial/licenses/                           Licences and notices of everything bundled.

HOW LOGINS AND AUDIO WORK (no credential harvesting)
  - Neon Dial never asks for, sees or stores your Apple/Spotify password. Apple: you type it into Apple's own page inside the built-in window.
    Spotify: you pick the device "Neon Dial FM" in your own Spotify app; Spotify hands the receiver a login token, kept under %USERPROFILE%\.neondial.
  - No music is bundled or downloaded by Neon Dial. Audio comes from your own account, through the app or player you already use.
  - No DRM is removed: Neon Dial records what your PC is already playing through Windows' own audio-capture API, the way a screen recorder would.
  - The main file makes no internet connections of its own and has no telemetry or update check. Only Apple's website (inside the built-in window) and the optional
    Spotify add-on talk to the internet, and only to Apple/Spotify.
  - The "Sign out and erase saved logins" button in the overlay deletes everything Neon Dial stored.

ANTIVIRUS NOTE
  The programs are not code-signed, so some antivirus tools may warn. They do: run a local audio server, start a helper, read other apps' audio level/volume and
  set their volume (that is how the music app is turned down while it plays through the game). Source and build are public (link above).

UNINSTALL
  Disable/remove the mod in Vortex (or delete the files listed above). To erase saved data also delete %USERPROFILE%\.neondial.

THIRD-PARTY SOFTWARE
  See licenses\THIRD_PARTY_NOTICES.md. Includes the LGPL library "lameenc" (MP3 encoder): you may replace _internal\lameenc*.pyd with your own build.
  Cyberpunk 2077 is a trademark of CD PROJEKT S.A.; Spotify and Apple Music belong to their owners. This is an unofficial fan project.
