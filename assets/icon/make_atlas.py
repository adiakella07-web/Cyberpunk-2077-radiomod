"""Regenerates neon_dial_icons.inkatlas (needs pythonnet + the WolvenKit console files + a .NET runtime). The result is committed, so CI does not need this.
usage: python make_atlas.py <depot path of the .xbm> <part name> <size px> <out file>"""
import sys, os, json
from pythonnet import load
load("coreclr", runtime_config="<path to WolvenKit console>/WolvenKit.CLI.runtimeconfig.json")
import clr
sys.path.append("<path to WolvenKit console>")
import System
for a in ("WolvenKit.RED4","WolvenKit.Core","WolvenKit.Common"):
    clr.AddReference(a)
from WolvenKit.RED4.Types import *
from WolvenKit.RED4.Types import Enums
inkTextureType, inkETextureResolution, ECookingPlatform = Enums.inkTextureType, Enums.inkETextureResolution, Enums.ECookingPlatform
from WolvenKit.RED4.Archive.CR2W import CR2WFile
from WolvenKit.RED4.CR2W.JSON import RedJsonSerializer

XBM = sys.argv[1]            # depot path of the texture, e.g. mod\neondial\neon_dial_icon.xbm
PART = sys.argv[2]
SIZE = int(sys.argv[3])
OUT = sys.argv[4]

atlas = inkTextureAtlas()
atlas.ActiveTexture = CEnum[inkTextureType](inkTextureType.StaticTexture)
atlas.TextureResolution = CEnum[inkETextureResolution](inkETextureResolution.UltraHD_3840_2160)
atlas.CookingPlatform = CEnum[ECookingPlatform](ECookingPlatform.PLATFORM_PC)
atlas.IsSingleTextureMode = CBool(True)
ref = CResourceAsyncReference[CBitmapTexture](ResourcePath.op_Implicit(XBM))
atlas.Texture = ref
m = inkTextureAtlasMapper()
m.PartName = CName.op_Implicit(PART)
I = CInt32.op_Implicit
r = Rect(); r.Left, r.Top, r.Right, r.Bottom = I(0), I(0), I(SIZE), I(SIZE)
m.ClippingRectInPixels = r
F = CFloat.op_Implicit
u = RectF(); u.Left, u.Top, u.Right, u.Bottom = F(0.0), F(0.0), F(1.0), F(1.0)
m.ClippingRectInUVCoords = u
atlas.Parts.Add(m)
slot = inkTextureSlot()
slot.Texture = CResourceAsyncReference[CBitmapTexture](ResourcePath.op_Implicit(XBM))
atlas.Slots[0] = slot
f = CR2WFile()
f.RootChunk = atlas
from WolvenKit.RED4.Archive.IO import CR2WWriter
fs = System.IO.File.Create(OUT)
w = CR2WWriter(fs)
w.WriteFile(f)
w.Dispose()
fs.Dispose()
print("wrote", OUT, os.path.getsize(OUT))
