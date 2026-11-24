# Privacy and security

Neon Dial plays your own music, so it is built so that **no login, token or account detail leaves your PC or shows up where it shouldn't**.

## Your logins
- **Apple Music (standalone mode):** you type your Apple ID and password only into Apple's own sign-in page, inside Neon Dial's built-in browser window.
  Neon Dial never sees them: it cannot read the page and runs only five fixed player commands (play, pause, next, previous, status).
  The window is locked to Apple's own sites (apple.com, icloud.com, mzstatic.com, ...); if anything redirects it elsewhere it is taken straight back.
  The session cookie lives in the embedded browser's profile (`%USERPROFILE%\.neondial\webview`), protected by Windows the same way a normal browser protects its cookies.
- **Spotify (standalone mode):** you never type a password into Neon Dial. You pick the device "Neon Dial FM" in your own Spotify app; Spotify hands the receiver a login token, saved in `%USERPROFILE%\.neondial\librespot\credentials.json`.
  That file is as sensitive as Spotify's own saved login (anything running as you could read it), so it is kept out of the game folder and out of every log.
  Until it has been paired once, the receiver advertises itself on your local network (that is how your Spotify app finds it). From the next start after pairing it **stops advertising**, so nobody else on your Wi-Fi can attach their account to it. Pair it on a network you trust.
- **Music app mode:** no login involved; it only presses play/pause on the app you already have open.
- **Sign out and erase saved logins** (in the in-game panel) deletes both of the above and clears the browser session.

## What can't leak
- **Logs and the in-game panel** are scrubbed before anything is stored or shown: account names, e-mail addresses, links, long tokens, cookies/passwords, **every file path** (including your Windows user name and the game folder) are replaced with placeholders, in the program and again in the in-game panel, so it is safe to screenshot or to use the panel's "Copy log to clipboard" button.
- **Nothing is uploaded.** There is no telemetry or analytics. The only outbound connections are the ones Spotify's receiver and Apple's website make to their own servers, exactly as their own apps would.
- **Network exposure:** everything listens on `127.0.0.1` only. The audio stream refuses browsers and other web pages (they always send headers the game's audio engine does not) and any request whose host isn't local, which blocks "a website you visit talking to your PC" and DNS-rebinding tricks.
  The optional browser control page is **off by default** (the in-game panel replaces it); if you turn it on (`"web_panel": true` in `%USERPROFILE%\.neondial\settings.json`) it also rejects foreign origins, non-JSON posts and unexpected hosts.
- The in-game status files in the mod folder contain only what is playing and a scrubbed activity log.

## Hardening in the program itself
- **No surprise programs:** it only starts the helper programs shipped next to it (never anything from the folder you launched it from), and never reads a config file from the working folder.
- **Everything is cleaned up:** the audio helper and the Spotify receiver are tied to Neon Dial (Windows job object + parent check), so they stop when it stops, even if it is killed from Task Manager. Your music app's volume is restored when you tune out, on exit and on the next start (only if the process is still the same one).
- **Commands are checked:** the in-game panel talks to the helper through a small text file in the mod folder. Any program on the PC could write to that file, so every command is checked against a fixed list and settings files only accept known keys and sane values.
- **Build integrity:** release files are built by GitHub Actions from this repository with every third-party input pinned (action commits, the Spotify receiver and RED4ext SDK commits, and the WolvenKit download hash); the build job has read-only permissions and only the separate release job can publish. Python packages are version-ranged, not hash-pinned.
- **Tests:** `tests/` checks log scrubbing, settings validation, the stream guard and the tune-in/out logic on every build.

## Limits (be aware)
- Malware already running as your Windows user can read your files, as with any program. Neon Dial can't defend against that.
- librespot (the Spotify receiver) is an unofficial Spotify client; using it may conflict with Spotify's terms.
- The executables are unsigned; some antivirus tools flag unsigned programs. The full source is in this repository and the release files are built by GitHub Actions from it.
