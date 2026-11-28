"""Removes files from the PyInstaller output that a Windows x64 build of Neon Dial never uses (other platforms' pywebview back-ends,
x86/arm64 copies, debug symbols, packaging tools). The packaged app's self-test (which opens the built-in browser and runs the
audio/stream code) runs AFTER this, so anything removed by mistake fails the build.
usage: python tools/prune_bundle.py companion/dist/NeonDial"""
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1]) / "_internal"
PATTERNS = [
    "**/*.pdb",
    "webview/platforms/android*", "webview/platforms/cocoa*", "webview/platforms/gtk*", "webview/platforms/qt*",
    "webview/platforms/cef*", "webview/**/pywebview-android.jar",
    # NOT pruned on purpose: webview/lib (incl. win-arm64 / win-x86 runtime folders: pywebview looks for them even on x64)
    # and clr_loader/ffi/dlls (its loader enumerates the architecture folders).
    "setuptools", "setuptools-*", "pkg_resources", "_distutils_hack", "numpy", "numpy-*", "numpy.libs",
]
removed = 0
for pat in PATTERNS:
    for path in sorted(root.glob(pat), key=lambda p: len(p.parts), reverse=True):
        if not path.exists():
            continue
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
        shutil.rmtree(path) if path.is_dir() else path.unlink()
        removed += size
        print("removed", path.relative_to(root).as_posix(), f"({size // 1024} KB)")
total = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
print(f"pruned {removed // 1024} KB; bundle is now {total // (1024 * 1024)} MB in {sum(1 for f in root.rglob('*') if f.is_file())} files")
