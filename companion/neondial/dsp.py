"""Optional 'texture' for the station: makes your music sound like it's coming over the Night City airwaves.

Pure standard library (audioop + a small look-up table): no numpy, so the program stays small."""
import array
import math
import os
import random
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import audioop

RATE = 44100
INT16_MAX = 32767


def _sinc_lp(fc, n):
    out = []
    for i in range(n):
        t = i - (n - 1) / 2
        x = 2 * fc / RATE * t
        s = 1.0 if x == 0 else math.sin(math.pi * x) / (math.pi * x)
        w = 0.54 - 0.46 * math.cos(2 * math.pi * i / (n - 1))          # Hamming window
        out.append(s * (2 * fc / RATE) * w)
    return out


def _band(lo, hi, n=513):
    h = _sinc_lp(hi, n)
    if lo:
        low = _sinc_lp(lo, n)
        h = [a - b for a, b in zip(h, low)]
    return h


def _taps(h):
    """Keep only taps that matter (the rest are far below the 16-bit noise floor)."""
    return [(k, c) for k, c in enumerate(h) if abs(c) > 6e-4]


# name -> (fir, drive, noise level (fraction of full scale), crackle probability per 0.1 s frame, bit depth or 0)
PRESETS = {
    "radio": (_band(240, 6800), 1.7, 0.0016, 0.02, 0),
    "lofi": (_band(380, 3900), 2.4, 0.0035, 0.06, 10),
    "warm": (_band(0, 11500, 257), 1.25, 0.0006, 0.0, 0),
}
_LUTS = {}


def _lut(drive, bits):
    """16-bit sample -> soft-saturated (and optionally bit-crushed) 16-bit sample."""
    key = (drive, bits)
    if key not in _LUTS:
        step = 1 << (16 - bits) if bits else 1
        table = []
        for v in range(-32768, 32768):
            y = math.tanh(v / 32768.0 * drive) / drive * 32768.0
            if step > 1:
                y = round(y / step) * step
            table.append(max(-32768, min(INT16_MAX, int(round(y)))))
        _LUTS[key] = table
    return _LUTS[key]


def _apply_lut(data, table):
    a = array.array("h")
    a.frombytes(data)
    return array.array("h", [table[v + 32768] for v in a]).tobytes()


class Texture:
    def __init__(self):
        self.mode = "off"
        self._tail = b""
        self._rng = random.Random()

    def set_mode(self, mode):
        self.mode = mode if mode in PRESETS else "off"
        self._tail = b""

    def _fir(self, x, preset_taps, n):
        """y[t] = sum_k h[k] * x[t-k] on interleaved stereo (each tap is one delayed copy, scaled and added)."""
        L = len(x)
        buf = (self._tail or b"\x00" * ((n - 1) * 4)) + x
        self._tail = buf[-(n - 1) * 4:]
        wide = audioop.lin2lin(buf, 2, 4)                 # work in 32-bit so rounding never reaches the audible range
        L4 = L * 2
        acc = b"\x00" * L4
        for k, c in preset_taps:
            off = (n - 1 - k) * 8
            acc = audioop.add(acc, audioop.mul(wide[off:off + L4], 4, c), 4)
        return audioop.lin2lin(acc, 4, 2)

    def process(self, pcm: bytes) -> bytes:
        if self.mode == "off" or not pcm:
            return pcm
        fir, drive, noise, crackle, bits = PRESETS[self.mode]
        n = len(fir)
        taps = _TAPS_CACHE.setdefault(self.mode, _taps(fir))
        y = self._fir(pcm, taps, n)
        y = _apply_lut(y, _lut(drive, 0))                                  # soft saturation (unity gain for quiet parts)
        if noise:
            y = audioop.add(y, audioop.mul(os.urandom(len(y)), 2, noise * math.sqrt(3)), 2)   # hiss (uniform noise)
        if crackle and self._rng.random() < crackle:                       # occasional crackle
            a = array.array("h")
            a.frombytes(y)
            for _ in range(self._rng.randint(1, 3)):
                i = self._rng.randrange(0, len(a) // 2) * 2
                imp = int(self._rng.uniform(-0.25, 0.25) * 32768)
                for j in (i, i + 1):
                    a[j] = max(-32768, min(INT16_MAX, a[j] + imp))
            y = a.tobytes()
        if bits:
            y = _apply_lut(y, _lut(1e-9, bits))                            # bit-crush only (drive ~0 = linear)
        return y


_TAPS_CACHE = {}
