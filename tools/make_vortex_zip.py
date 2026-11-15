"""Assemble the Vortex-installable zip.
usage: python tools/make_vortex_zip.py <NeonDial.exe> <NeonDial.dll> <NeonDialAudio.exe> [out.zip] [librespot.exe]"""
import pathlib
import sys
import zipfile

root = pathlib.Path(__file__).resolve().parent.parent
pkg = root / "vortex_package"
exe, dll, helper = (pathlib.Path(a) for a in sys.argv[1:4])
out = pathlib.Path(sys.argv[4] if len(sys.argv) > 4 else root / "NeonDial-vortex.zip")
librespot = pathlib.Path(sys.argv[5]) if len(sys.argv) > 5 else None
for f in (exe, dll, helper):
    if not f.exists():
        sys.exit(f"missing: {f}")
dest = "red4ext/plugins/NeonDial/"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in pkg.rglob("*"):
        if f.is_file():
            z.write(f, f.relative_to(pkg).as_posix())
    z.write(exe, dest + "NeonDial.exe")
    z.write(dll, dest + "NeonDial.dll")
    z.write(helper, dest + "NeonDialAudio.exe")
    if librespot and librespot.exists():
        z.write(librespot, dest + "librespot.exe")
        print("included librespot")
print("Wrote", out)
