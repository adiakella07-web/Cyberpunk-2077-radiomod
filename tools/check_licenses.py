"""Cross-checks the Python packages that are really inside the packaged app against the licence notices we ship, and refuses
copyleft/unknown licences (the one deliberate exception is the replaceable LGPL library lameenc).
usage: python tools/check_licenses.py companion/dist/NeonDial licenses/PYTHON_PACKAGES_LICENSES.txt"""
import pathlib
import re
import sys
from email.parser import Parser

internal = pathlib.Path(sys.argv[1]) / "_internal"
notices = pathlib.Path(sys.argv[2]).read_text(errors="replace").lower()
OK = re.compile(r"\b(mit|bsd|apache|psf|python software foundation|isc|zlib|0bsd|cc0|unlicense|mpl)\b", re.I)
COPYLEFT = re.compile(r"\b(a?gpl|lgpl|gnu (lesser )?general public)\b", re.I)
ALLOWED_COPYLEFT = {"lameenc"}


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


problems, seen = [], []
for meta in sorted(internal.glob("*.dist-info/METADATA")):
    msg = Parser().parsestr(meta.read_text(errors="replace"))
    name, ver = msg.get("Name", meta.parent.name), msg.get("Version", "?")
    lic = " | ".join(filter(None, [msg.get("License-Expression"), msg.get("License")] +
                            [c for c in (msg.get_all("Classifier") or []) if c.startswith("License")]))
    seen.append(f"{name} {ver}: {lic[:80] or 'NO LICENCE METADATA'}")
    n = norm(name)
    if n not in re.sub(r"[-_.]+", "-", notices):
        problems.append(f"{name} is inside the app but missing from the shipped licence notices")
    if not lic.strip():
        problems.append(f"{name}: no licence metadata")
    elif COPYLEFT.search(lic) and n not in ALLOWED_COPYLEFT:
        problems.append(f"{name}: copyleft licence not on the allow-list ({lic[:60]})")
    elif not OK.search(lic) and not (COPYLEFT.search(lic) and n in ALLOWED_COPYLEFT):
        problems.append(f"{name}: unrecognised licence ({lic[:60]})")
print("\n".join(seen))
for forbidden in ("numpy", "setuptools", "pkg_resources"):
    if (internal / forbidden).exists():
        problems.append(f"{forbidden} should not be bundled")
if problems:
    print("PROBLEMS:")
    print("\n".join(" - " + p for p in problems))
    sys.exit(1)
print(f"licence check passed for {len(seen)} packages")
