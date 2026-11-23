# Pre-upload checklist (before you put Neon Dial on Nexus Mods or opt in to Donation Points)

The build already does the mechanical checks for you (`tools/verify_release.py` runs in CI and fails the build on any problem):
- every file in each zip is listed in `MANIFEST.md`/`MANIFEST.json` with its origin, licence and SHA-256, and the hashes match;
- the licence folder (Python packages, Python, RED4ext SDK, Neon Dial's own licence, and for the add-on librespot + its Rust crates) is present;
- no unexpected executables (only `NeonDial.exe`, `NeonDialAudio.exe` and, in the add-on, `librespot.exe`);
- no tokens, keys, passwords or e-mail addresses in any of the text files (init.lua, metadata.json, README, web page, manifest).

## You, by hand
1. Download the release files from the GitHub Releases page (not from your build folder) and unzip them somewhere. Open `red4ext/plugins/NeonDial/MANIFEST.md` and skim it: every row should have an origin and a licence you are happy with.
2. Install the main file with Vortex on a clean setup (CET + RED4ext + RadioExt only), launch the game, and confirm: the station shows with its icon, Neon Dial window opens in the CET overlay, music plays, sign-out button works.
3. Upload both zips to a private virus-scan site if you like (e.g. VirusTotal) and note any detections; unsigned programs sometimes get false positives. Say so on the page if so.
4. Take your own screenshots; write the page from `docs/NEXUS_SUBMISSION.md` (keep the AI disclosure).
5. Nexus: set the AI tag that matches reality (the code was AI-generated), list CET / RED4ext / RadioExt as required mods, upload the main file as Main and the Spotify add-on as Optional.
6. Contact the RadioExt author and Nexus support using the templates in `docs/NEXUS_SUBMISSION.md`.
7. Only after the page is published and approved: read the Donation Points rules again and opt in from your account (the rules, as quoted to me, need an adult account in good standing with at least one published mod on a supported game; confirm on Nexus's page).

## What the manifest cannot tell you
Whether Nexus accepts AI-generated code as "original work" for Donation Points, whether CD PROJEKT RED is comfortable with a Donation Points reward on a mod, and whether Spotify/Apple object to the integrations. Those are judgement calls for you and, where relevant, for Nexus staff.
