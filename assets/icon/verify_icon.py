import pathlib, sys
from PIL import Image
files = list(pathlib.Path(sys.argv[1]).rglob("*.png")) + list(pathlib.Path(sys.argv[1]).rglob("*.tga")) + list(pathlib.Path(sys.argv[1]).rglob("*.dds"))
if not files:
    sys.exit("no exported texture found")
im = Image.open(files[0]).convert("RGBA")
a = im.split()[3]
lo, hi = a.getextrema()
print("exported", files[0], im.size, "alpha range", lo, hi)
if hi < 200 or lo > 50:
    sys.exit("alpha channel lost in texture import")
