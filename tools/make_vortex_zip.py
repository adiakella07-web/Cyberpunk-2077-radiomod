"""Assemble the Vortex-installable zip.
usage: python tools/make_vortex_zip.py <NeonDial.exe> <NeonDial.dll> <NeonDialAudio.exe> [out.zip] [librespot.exe] [NeonDial.archive]"""
import json
import pathlib
import sys
import zipfile

root = pathlib.Path(__file__).resolve().parent.parent
pkg = root / "vortex_package"
exe, dll, helper = (pathlib.Path(a) for a in sys.argv[1:4])
out = pathlib.Path(sys.argv[4] if len(sys.argv) > 4 else root / "NeonDial-vortex.zip")
librespot = pathlib.Path(sys.argv[5]) if len(sys.argv) > 5 else None
icon_archive = pathlib.Path(sys.argv[6]) if len(sys.argv) > 6 else None
for f in (exe, dll, helper):
    if not f.exists():
        sys.exit(f"missing: {f}")
dest = "red4ext/plugins/NeonDial/"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in pkg.rglob("*"):
        if f.is_file():
            rel = f.relative_to(pkg).as_posix()
            if rel.endswith("radios/NeonDial/metadata.json") and icon_archive and icon_archive.exists():
                meta = json.loads(f.read_text())
                meta["customIcon"] = {"inkAtlasPath": "mod\\neondial\\neon_dial_icons.inkatlas",
                                      "inkAtlasPart": "neon_dial", "useCustom": True}
                z.writestr(rel, json.dumps(meta, indent=4))
                continue
            z.write(f, rel)
    z.write(exe, dest + "NeonDial.exe")
    z.write(dll, dest + "NeonDial.dll")
    z.write(helper, dest + "NeonDialAudio.exe")
    if icon_archive and icon_archive.exists():
        z.write(icon_archive, "archive/pc/mod/NeonDial.archive")
        print("included custom icon archive")
    if librespot and librespot.exists():
        z.write(librespot, dest + "librespot.exe")
        print("included librespot")
print("Wrote", out)
