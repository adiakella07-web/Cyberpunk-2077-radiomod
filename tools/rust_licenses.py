"""Reads `cargo metadata --format-version 1` JSON on stdin and prints every Rust dependency with its licence and source.
Used to ship an honest third-party notice list with the Spotify add-on."""
import json
import sys

meta = json.load(sys.stdin)
root = set(meta.get("workspace_members", []))
rows = []
for p in meta["packages"]:
    if p["id"] in root:
        continue
    rows.append((p["name"], p["version"], p.get("license") or "see source", p.get("repository") or p.get("homepage") or "crates.io"))
print("Rust crates compiled into librespot.exe (name, version, licence, source). Each is used under the licence shown.")
print("-" * 100)
for name, ver, lic, repo in sorted(rows):
    print(f"{name} {ver} | {lic} | {repo}")
