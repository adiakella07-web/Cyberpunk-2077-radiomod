"""Builds the two release files, each with a manifest (origin, licence and sha256 of every file).
  NeonDial-<ver>.zip               main mod (Vortex-ready)
  NeonDial-SpotifyAddon-<ver>.zip  optional add-on: the Spotify receiver for "Standalone Spotify" mode
usage: python tools/make_packages.py --version v1.6.0 --dist companion/dist/NeonDial --dll NeonDial.dll --helper NeonDialAudio.exe
          --licenses licenses --out out [--icon NeonDial.archive] [--librespot librespot.exe]"""
import argparse
import json
import pathlib
import sys
import zipfile

root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "tools"))
import manifest  # noqa: E402

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


def write_zip(path, entries, manifest_name):
    md, js = manifest.build(entries)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in entries:
            z.writestr(arc, data)
        z.writestr(PLUGIN + manifest_name + ".md", md)
        z.writestr(PLUGIN + manifest_name + ".json", js)
    print("Wrote", path, f"({len(entries)} files)")


# ---------------- main file
entries = []
for f in sorted(pkg.rglob("*")):
    if not f.is_file():
        continue
    rel = f.relative_to(pkg).as_posix()
    data = f.read_bytes()
    if rel.endswith("radios/NeonDial/metadata.json") and icon and icon.exists():
        meta = json.loads(data)
        meta["customIcon"] = {"inkAtlasPath": "mod\\neondial\\neon_dial_icons.inkatlas",
                              "inkAtlasPart": "neon_dial", "useCustom": True}
        data = json.dumps(meta, indent=4).encode()
    entries.append((rel, data))
for f in sorted(dist.rglob("*")):                   # the companion program (onedir: the .exe plus its _internal folder)
    if f.is_file():
        entries.append((PLUGIN + f.relative_to(dist).as_posix(), f.read_bytes()))
entries.append((PLUGIN + "NeonDial.dll", pathlib.Path(a.dll).read_bytes()))
entries.append((PLUGIN + "NeonDialAudio.exe", pathlib.Path(a.helper).read_bytes()))
for f in sorted(lic.rglob("*")):
    if f.is_file() and "librespot" not in f.name.lower():
        entries.append((PLUGIN + "licenses/" + f.relative_to(lic).as_posix(), f.read_bytes()))
entries.append((PLUGIN + "licenses/NeonDial-LICENSE.txt", (root / "LICENSE").read_bytes()))
if icon and icon.exists():
    entries.append(("archive/pc/mod/NeonDial.archive", icon.read_bytes()))
write_zip(out / f"NeonDial-{a.version}.zip", entries, "MANIFEST")

# ---------------- optional Spotify add-on
if a.librespot and pathlib.Path(a.librespot).exists():
    add = [(PLUGIN + "librespot.exe", pathlib.Path(a.librespot).read_bytes())]
    for f in sorted(lic.rglob("*")):
        if f.is_file() and "librespot" in f.name.lower():
            add.append((PLUGIN + "licenses/" + f.relative_to(lic).as_posix(), f.read_bytes()))
    add.append((PLUGIN + "SPOTIFY_ADDON_README.txt", (root / "docs" / "ADDON_README.txt").read_bytes()))
    write_zip(out / f"NeonDial-SpotifyAddon-{a.version}.zip", add, "SPOTIFY_ADDON_MANIFEST")
