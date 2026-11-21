# Third-party notices

Neon Dial's own code is MIT licensed (see `LICENSE`). It ships with, or was built using, the following. Full licence texts are in the
`licenses/` folder that is part of every release file (`red4ext/plugins/NeonDial/licenses/`).

## Inside the main file (NeonDial-<version>.zip)
| Component | Licence | Notes |
|---|---|---|
| Python runtime | PSF-2.0 | `licenses/PYTHON-LICENSE.txt` |
| aiohttp and its dependencies, numpy, psutil, pywebview, pythonnet, clr-loader, winrt-* packages | Apache-2.0 / BSD-3-Clause / MIT (per package) | exact list and full texts: `licenses/PYTHON_PACKAGES_LICENSES.txt` |
| **lameenc** (wraps the LAME MP3 encoder) | **LGPL-3.0-or-later** | see below |
| PyInstaller bootloader (packs the program) | GPL-2.0 with the PyInstaller bootloader exception | the exception lets the packed program use any licence |
| RED4ext SDK headers (compiled into `NeonDial.dll`) | MIT | `licenses/RED4ext-SDK-LICENSE.txt` |

### LGPL notice (lameenc / LAME)
Neon Dial uses the **lameenc** library (https://github.com/chrisstaite/lameenc, LGPL-3.0-or-later) which contains the **LAME** MP3 encoder
(https://lame.sourceforge.io/, LGPL). The program is shipped as a folder (not a single packed file) specifically so that this library stays a
separate, replaceable file: **you may replace `_internal\lameenc*.pyd` with your own build of lameenc** and Neon Dial will use it.
The corresponding source code of lameenc and LAME is available at the links above. The LGPL-3.0 text is in `licenses/PYTHON_PACKAGES_LICENSES.txt`.
Neon Dial's own source is at https://github.com/adiakella07-web/Cyberpunk-2077-radiomod.

## Optional Spotify add-on (NeonDial-SpotifyAddon-<version>.zip)
| Component | Licence | Notes |
|---|---|---|
| **librespot** (https://github.com/librespot-org/librespot) | MIT | `licenses/librespot-LICENSE.txt`; the Rust crates compiled into it are listed with their licences in `licenses/librespot-dependencies.txt` |

## Used only while building (nothing of it is shipped)
- **WolvenKit** CLI (https://github.com/WolvenKit/WolvenKit) converts the icon image into the game's texture format and packs it into `NeonDial.archive`. The icon artwork itself is drawn by `assets/icon/make_icon.py` (original work, no third-party art).

## Required but NOT included (installed separately by the player)
Cyber Engine Tweaks, RED4ext, RadioExt, Microsoft Edge WebView2 Runtime (only for Standalone Apple Music).

## Trademarks
Cyberpunk 2077 is a trademark of CD PROJEKT S.A. Spotify and Apple Music are trademarks of their owners. Neon Dial is an unofficial fan project and is
not affiliated with or endorsed by any of them.
