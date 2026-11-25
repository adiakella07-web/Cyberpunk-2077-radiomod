"""Pre-upload verification of the release zips. Exits non-zero (and the build fails) on any problem.
usage: python tools/verify_release.py out/NeonDial-*.zip"""
import hashlib
import json
import re
import sys
import zipfile

PLUGIN = "red4ext/plugins/NeonDial/"
MAIN_REQUIRED = [
    "bin/x64/plugins/cyber_engine_tweaks/mods/NeonDial/init.lua",
    "bin/x64/plugins/cyber_engine_tweaks/mods/radioExt/radios/NeonDial/metadata.json",
    PLUGIN + "NeonDial.exe", PLUGIN + "NeonDial.dll", PLUGIN + "NeonDialAudio.exe", PLUGIN + "README.txt",
    PLUGIN + "MANIFEST.md", PLUGIN + "MANIFEST.json", PLUGIN + "licenses/THIRD_PARTY_NOTICES.md",
    PLUGIN + "licenses/PYTHON_PACKAGES_LICENSES.txt", PLUGIN + "licenses/NeonDial-LICENSE.txt",
    PLUGIN + "licenses/RED4ext-SDK-LICENSE.txt", PLUGIN + "licenses/PYTHON-LICENSE.txt",
]
ADDON_REQUIRED = [PLUGIN + "librespot.exe", PLUGIN + "SPOTIFY_ADDON_README.txt", PLUGIN + "SPOTIFY_ADDON_MANIFEST.md",
                  PLUGIN + "licenses/librespot-LICENSE.txt", PLUGIN + "licenses/librespot-dependencies.txt"]
ALLOWED_EXE = {"NeonDial.exe", "NeonDialAudio.exe", "librespot.exe"}
SECRET = re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
                    r"(?i:client_secret|api[_-]?key|password)\s*[:=]\s*[\"'][^\"']{6,}|Bearer\s+[A-Za-z0-9._-]{20,}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
TEXT_EXT = (".lua", ".json", ".txt", ".md", ".html", ".css", ".js", ".toml", ".bat")
problems = []


def check(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    is_addon = "SpotifyAddon" in path
    for req in (ADDON_REQUIRED if is_addon else MAIN_REQUIRED):
        if req not in names:
            problems.append(f"{path}: missing {req}")
    mname = PLUGIN + ("SPOTIFY_ADDON_MANIFEST.json" if is_addon else "MANIFEST.json")
    if mname in names:
        listed = {r["path"]: r["sha256"] for r in json.loads(z.read(mname))}
        for n in names:
            if n.endswith("/") or n.endswith("MANIFEST.json") or n.endswith("MANIFEST.md"):
                continue
            if n not in listed:
                problems.append(f"{path}: {n} is not in the manifest")
            elif hashlib.sha256(z.read(n)).hexdigest() != listed[n]:
                problems.append(f"{path}: {n} does not match the manifest")
    for n in names:
        low = n.lower()
        if low.endswith(".pdb") or "/numpy" in low or "/setuptools" in low or "/pkg_resources" in low or "platforms/android" in low or "platforms/cocoa" in low or "platforms/gtk" in low or "platforms/qt" in low or "x86.dll" in low:
            problems.append(f"{path}: file that should have been pruned: {n}")
        base = n.rsplit("/", 1)[-1]
        if n.lower().endswith(".exe") and base not in ALLOWED_EXE:
            problems.append(f"{path}: unexpected executable {n}")
        if n.lower().endswith(TEXT_EXT) and not n.endswith("/"):
            text = z.read(n).decode("utf-8", "replace")
            if SECRET.search(text):
                problems.append(f"{path}: possible secret in {n}")
            if "/licenses/" not in n and EMAIL.search(text):
                m = EMAIL.search(text).group(0)
                if not m.endswith(("@users.noreply.github.com", "@example.com")):
                    problems.append(f"{path}: e-mail address in {n}")
    print(f"checked {path}: {len(names)} files")


for p in sys.argv[1:]:
    check(p)
if problems:
    print("PROBLEMS:")
    print("\n".join(" - " + x for x in problems))
    sys.exit(1)
print("release verification passed")
