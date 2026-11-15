"""Optional 'texture' for the station: makes your music sound like it's coming over the Night City airwaves."""
import numpy as np

RATE = 44100


def _sinc_lp(fc, n):
    t = np.arange(n) - (n - 1) / 2
    h = np.sinc(2 * fc / RATE * t) * (2 * fc / RATE)
    return h * np.hamming(n)


def _band(lo, hi, n=513):
    h = _sinc_lp(hi, n)
    if lo:
        h = h - _sinc_lp(lo, n)
    return h.astype(np.float64)


# name -> (fir, drive, noise level, crackle prob per frame, bit depth or 0)
PRESETS = {
    "radio": (_band(240, 6800), 1.7, 0.0016, 0.02, 0),
    "lofi": (_band(380, 3900), 2.4, 0.0035, 0.06, 10),
    "warm": (_band(0, 11500, 257), 1.25, 0.0006, 0.0, 0),
}


class Texture:
    def __init__(self):
        self.mode = "off"
        self._tail = None
        self._rng = np.random.default_rng()

    def set_mode(self, mode):
        self.mode = mode if mode in PRESETS else "off"
        self._tail = None

    def process(self, pcm: bytes) -> bytes:
        if self.mode == "off" or not pcm:
            return pcm
        fir, drive, noise, crackle, bits = PRESETS[self.mode]
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float64).reshape(-1, 2) / 32768.0
        n = len(fir)
        if self._tail is None:
            self._tail = np.zeros((n - 1, 2))
        xx = np.vstack([self._tail, x])
        self._tail = xx[-(n - 1):]
        y = np.stack([np.convolve(xx[:, c], fir, mode="valid") for c in range(2)], axis=1)
        y = np.tanh(y * drive) / drive                               # soft saturation (unity gain for quiet parts)
        if noise:
            y += noise * self._rng.standard_normal(y.shape)           # hiss
        if crackle and self._rng.random() < crackle:                  # occasional crackle
            pos = self._rng.integers(0, len(y), size=int(self._rng.integers(1, 4)))
            y[pos] += self._rng.uniform(-0.25, 0.25, size=(len(pos), 1))
        if bits:
            q = 2 ** (bits - 1)
            y = np.round(y * q) / q
        return (np.clip(y, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
