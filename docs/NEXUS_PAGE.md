# Neon Dial: Your Music as a Radio Station (Nexus page draft)

**Short description:** Adds "Neon Dial FM" to the radio list and plays your open Apple Music / Spotify playlist through the game's radio mix. No logins or API keys.

## Description
Open Apple Music or Spotify on your PC, load a playlist, and tune to **Neon Dial FM**, the last station in the radio list. Tune away and it pauses.

## Requirements
- Cyber Engine Tweaks
- RED4ext
- RadioExt
- Windows 10/11, Apple Music or Spotify desktop app

## Installation
Install with Vortex, enable, deploy. Start your music app, launch the game, tune to Neon Dial FM.

## How it works
A helper starts with the game. When you tune in it plays your music app and routes just that app's audio into the game's radio, so radio volume, car muffling and station switching all work. Switch away and the music pauses; switch back and it resumes.

## Known issues / limits
- Needs Windows 10 2004+/11 (process loopback). If capture fails it falls back to playing through your speakers.
- Unsigned helper exe may trigger antivirus false positives; source is on GitHub.

## Permissions / credits
Source: https://github.com/adiakella07-web/Cyberpunk-2077-radiomod (MIT). Thanks to RadioExt, RED4ext and CET authors.
