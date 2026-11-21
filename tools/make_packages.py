"""Builds the two release files.
  NeonDial-<ver>.zip               main mod (Vortex-ready)
  NeonDial-SpotifyAddon-<ver>.zip  optional add-on: the Spotify receiver for "Standalone Spotify" mode
usage: python tools/make_packages.py --version v1.6.0 --dist companion/dist/NeonDial --dll NeonDial.dll --helper NeonDialAudio.exe
          --licenses licenses --out out [--icon NeonDial.archive] [--librespot librespot.exe]"""
import argparse
import json
import pathlib
import zipfile

root = pathlib.Path(__file__).resolve().parent.parent
pkg = root / "vortex_package"
PLUGIN = "red4ext/plugins/NeonDial/"

ap = argparse.ArgumentParser()
ap.add_argument("--version", required=True)
ap.add_argument("--dist", required=True)
ap.add_argument("--dll", required=True)
ap.add_argument("--helper", required=True)
ap.add_argument("--licenses", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--icon")
ap.add_argument("--librespot")
a = ap.parse_args()
out = pathlib.Path(a.out)
out.mkdir(parents=True, exist_ok=True)
dist, lic = pathlib.Path(a.dist), pathlib.Path(a.licenses)
icon = pathlib.Path(a.icon) if a.icon else None

main = out / f"NeonDial-{a.version}.zip"
with zipfile.ZipFile(main, "w", zipfile.ZIP_DEFLATED) as z:
    for f in pkg.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(pkg).as_posix()
        if rel.endswith("radios/NeonDial/metadata.json") and icon and icon.exists():
            meta = json.loads(f.read_text())
            meta["customIcon"] = {"inkAtlasPath": "mod\\neondial\\neon_dial_icons.inkatlas",
                                  "inkAtlasPart": "neon_dial", "useCustom": True}
            z.writestr(rel, json.dumps(meta, indent=4))
        else:
            z.write(f, rel)
    for f in dist.rglob("*"):                       # the companion program (onedir: the .exe plus its _internal folder)
        if f.is_file():
            z.write(f, PLUGIN + f.relative_to(dist).as_posix())
    z.write(a.dll, PLUGIN + "NeonDial.dll")
    z.write(a.helper, PLUGIN + "NeonDialAudio.exe")
    for f in lic.rglob("*"):
        if f.is_file() and "librespot" not in f.name.lower():
            z.write(f, PLUGIN + "licenses/" + f.relative_to(lic).as_posix())
    z.write(root / "LICENSE", PLUGIN + "licenses/NeonDial-LICENSE.txt")
    if icon and icon.exists():
        z.write(icon, "archive/pc/mod/NeonDial.archive")
print("Wrote", main)

if a.librespot and pathlib.Path(a.librespot).exists():
    add = out / f"NeonDial-SpotifyAddon-{a.version}.zip"
    with zipfile.ZipFile(add, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(a.librespot, PLUGIN + "librespot.exe")
        for f in lic.rglob("*"):
            if f.is_file() and "librespot" in f.name.lower():
                z.write(f, PLUGIN + "licenses/" + f.relative_to(lic).as_posix())
        z.write(root / "docs" / "ADDON_README.txt", PLUGIN + "SPOTIFY_ADDON_README.txt")
    print("Wrote", add)
