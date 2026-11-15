"""Assemble the Vortex-installable zip.
usage: python tools/make_vortex_zip.py <NeonDial.exe> <NeonDial.dll> [out.zip]"""
import pathlib
import sys
import zipfile

root = pathlib.Path(__file__).resolve().parent.parent
pkg = root / "vortex_package"
exe, dll = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
out = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else root / "NeonDial-vortex.zip")
for f in (exe, dll):
    if not f.exists():
        sys.exit(f"missing: {f}")
dest = "red4ext/plugins/NeonDial/"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in pkg.rglob("*"):
        if f.is_file():
            z.write(f, f.relative_to(pkg).as_posix())
    z.write(exe, dest + "NeonDial.exe")
    z.write(dll, dest + "NeonDial.dll")
print("Wrote", out)
