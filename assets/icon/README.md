Neon Dial station icon.
- make_icon.py draws the 256x256 white-on-transparent glyph (the game tints it).
- neon_dial_icons.inkatlas is the game's icon atlas (part `neon_dial`) pointing at `mod\neondial\neon_dial_icon.xbm`.
  It was generated with make_atlas.py using WolvenKit's libraries and verified by round-tripping with WolvenKit's `convert serialize`.
- CI converts the PNG to `.xbm` with the WolvenKit CLI (Windows only), packs both into `NeonDial.archive`, and ships it in `archive/pc/mod/`.
