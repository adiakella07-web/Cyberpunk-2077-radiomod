"""PCM -> MP3 live stream.

RadioExt connects to the stream URL and plays it through the game's own audio engine (FMOD), so the
in-game radio volume, muffling and station switching all apply to it.
"""
import asyncio
import time

import lameenc

from .dsp import Texture

RATE, CH = 44100, 2
BPS = RATE * CH * 2                  # bytes per second of S16 PCM
FRAME_SEC = 0.1
FRAME_BYTES = int(BPS * FRAME_SEC)   # 17640 (multiple of 4)
MAX_BUFFER = BPS                     # 1 s look-ahead for back-pressured sources (demo)
PRIME_BYTES = int(BPS * 0.08)        # live sources: build this much cushion before playing
LIVE_MAX = int(BPS * 0.25)           # live sources: never hold more than this (drops oldest)
PREROLL_SEC = 0.8


def _encoder():
    e = lameenc.Encoder()
    e.set_bit_rate(320)   # higher rate = the game's fixed-size stream buffer fills sooner
    e.set_in_sample_rate(RATE)
    e.set_channels(CH)
    e.set_quality(2)
    return e


class AudioEngine:
    def __init__(self):
        self.buf = bytearray()
        self.clients: set[asyncio.Queue] = set()
        self._enc = _encoder()
        self._primed = False
        self._warned = False
        self.texture = Texture()
        self.hold = False                 # set by sources that want audio kept while idle
        # Sent instantly to every new listener so the game's stream buffer fills at once and the
        # station "starts" immediately (music then follows live).
        pre = _encoder()
        self.preroll = bytes(pre.encode(b"\x00" * int(BPS * PREROLL_SEC)) + pre.flush())

    # -- source side ------------------------------------------------
    def room(self) -> bool:
        return len(self.buf) < MAX_BUFFER

    def feed(self, pcm: bytes):
        self.buf += pcm

    def feed_live(self, pcm: bytes):
        """For real-time sources (capture): never block, keep latency bounded."""
        self.buf += pcm
        excess = (len(self.buf) - LIVE_MAX) // 4 * 4
        if excess > 0:
            del self.buf[:excess]

    def flush(self):
        self.buf.clear()
        self._primed = False

    # -- client side ------------------------------------------------
    def add_client(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=200)
        self.clients.add(q)
        return q

    def remove_client(self, q):
        self.clients.discard(q)

    def _publish(self, data: bytes):
        for q in list(self.clients):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(data)

    async def run(self):
        """Real-time pacer. Always emits audio (silence when idle) so the game never sees a dead stream."""
        next_t = time.monotonic()
        silence = b"\x00" * FRAME_BYTES
        while True:
            if self.hold and not self.clients:
                # nobody is tuned in: keep any buffered audio for when they come back
                next_t += FRAME_SEC
                await asyncio.sleep(max(0, next_t - time.monotonic()))
                continue
            if not self._primed and len(self.buf) >= FRAME_BYTES + PRIME_BYTES:
                self._primed = True
            if self._primed and len(self.buf) >= FRAME_BYTES:
                chunk = bytes(self.buf[:FRAME_BYTES])
                del self.buf[:FRAME_BYTES]
            else:
                chunk = silence
                self._primed = False          # starved: rebuild the cushion
            try:
                if self.clients and self.texture.mode != "off":
                    chunk = self.texture.process(chunk)
                mp3 = self._enc.encode(chunk)
                if mp3 and self.clients:
                    self._publish(bytes(mp3))
            except Exception as e:                    # keep the stream alive; drop the texture if it is the culprit
                if self.texture.mode != "off":
                    self.texture.set_mode("off")
                if not self._warned:
                    self._warned = True
                    from .log import log
                    log(f"audio frame error ({type(e).__name__}); texture switched off")
            next_t += FRAME_SEC
            delay = next_t - time.monotonic()
            if delay < -1:
                next_t = time.monotonic()
            await asyncio.sleep(max(0, delay))
