"""Neon Dial station icon: chamfered HUD frame, broadcast arcs, tuner scale with needle, "FM". White on transparent (game tints it)."""
import math
from PIL import Image, ImageDraw
S, N = 4, 256
img = Image.new("RGBA", (N * S, N * S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
white = (255, 255, 255, 255)
P = lambda x, y: (x * S, y * S)
def line(a, b, w): d.line([P(*a), P(*b)], fill=white, width=int(w * S))
def dot(x, y, r): d.ellipse([P(x - r, y - r), P(x + r, y + r)], fill=white)

# chamfered frame, open at the bottom-right chamfer
c, m = 38, 9
pts = [(c, m), (N - c, m), (N - m, c), (N - m, N - c), (N - c, N - m), (c, N - m), (m, N - c), (m, c)]
for i in range(8):
    if i == 3:                      # gap
        continue
    a, b = pts[i], pts[(i + 1) % 8]
    line(a, b, 11)
for (x, y) in pts:
    dot(x, y, 5.5)

# broadcast arcs from a dot
cx, cy = 128, 104
dot(cx, cy, 9)
for r, w in ((30, 8), (52, 8), (74, 8)):
    d.arc([P(cx - r, cy - r), P(cx + r, cy + r)], 215, 325, fill=white, width=int(w * S))

# tuner scale + needle
y0 = 150
line((44, y0), (212, y0), 5)
for i in range(0, 22):
    x = 44 + i * (168 / 21)
    h = 18 if i % 5 == 0 else 9
    line((x, y0), (x, y0 + h), 4 if i % 5 else 6)
nx = 150
d.polygon([P(nx - 9, y0 - 24), P(nx + 9, y0 - 24), P(nx, y0 - 8)], fill=white)
line((nx, y0 - 8), (nx, y0 + 24), 5)

# "FM"
ty, bh = 186, 40
fx = 64
line((fx, ty), (fx, ty + bh), 9)
line((fx - 4, ty), (fx + 30, ty), 9)
line((fx - 4, ty + 19), (fx + 24, ty + 19), 8)
mx = 118
line((mx, ty + bh), (mx, ty), 9)
line((mx - 4, ty + 3), (mx + 22, ty + bh - 6), 8)
line((mx + 44, ty + 3), (mx + 22, ty + bh - 6), 8)
line((mx + 44, ty), (mx + 44, ty + bh), 9)

img = img.resize((N, N), Image.LANCZOS)
import sys, os
out = sys.argv[1] if len(sys.argv) > 1 else "neon_dial_icon.png"
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
img.save(out)
