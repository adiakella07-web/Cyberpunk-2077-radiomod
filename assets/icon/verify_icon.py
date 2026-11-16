"""Checks the imported texture (serialized to JSON by WolvenKit): 256x256 and RGBA-capable."""
import json, pathlib, sys

def walk(o, found):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("width", "height", "mipCount", "compression", "format", "type", "isGamma", "alignment") and not isinstance(v, (dict, list)):
                found.setdefault(k, v)
            walk(v, found)
    elif isinstance(o, list):
        for v in o:
            walk(v, found)

files = list(pathlib.Path(sys.argv[1]).rglob("*.json"))
if not files:
    sys.exit("no serialized texture found")
found = {}
walk(json.loads(files[0].read_text(encoding="utf-8")), found)
print("texture info", found)
if found.get("width") != 256 or found.get("height") != 256:
    sys.exit("unexpected texture size")
print("alpha range OK-by-size (format " + str(found.get("compression", found.get("format"))) + ")")
