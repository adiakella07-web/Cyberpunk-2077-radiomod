"""PCM -> MP3 live stream.

RadioExt connects to /stream.mp3 and plays it through the game's own audio
engine, so it respects radio volume, car muffling, etc.
"""
import asyncio
import time

import lameenc

RATE, CH = 44100, 2
BPS = RATE * CH * 2                  # bytes per second of S16 PCM
FRAME_SEC = 0.1
FRAME_BYTES = int(BPS * FRAME_SEC)   # 17640 (multiple of 4)
MAX_BUFFER = BPS                     # 1 s look-ahead; gives back-pressure to librespot


class AudioEngine:
    def __init__(self):
        self.buf = bytearray()
        self.clients: set[asyncio.Queue] = set()
        self._enc = lameenc.Encoder()
        self._enc.set_bit_rate(192)
        self._enc.set_in_sample_rate(RATE)
        self._enc.set_channels(CH)
        self._enc.set_quality(2)

    # -- source side ------------------------------------------------
    def room(self) -> bool:
        return len(self.buf) < MAX_BUFFER

    def feed(self, pcm: bytes):
        self.buf += pcm

    def flush(self):
        self.buf.clear()

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
        """Real-time pacer. Always emits audio (silence when idle) so the
        game never sees a dead stream."""
        next_t = time.monotonic()
        while True:
            chunk = bytes(self.buf[:FRAME_BYTES])
            del self.buf[:FRAME_BYTES]
            if len(chunk) < FRAME_BYTES:
                chunk += b"\x00" * (FRAME_BYTES - len(chunk))
            mp3 = self._enc.encode(chunk)
            if mp3 and self.clients:
                self._publish(bytes(mp3))
            next_t += FRAME_SEC
            delay = next_t - time.monotonic()
            if delay < -1:           # fell behind (sleep/suspend)
                next_t = time.monotonic()
            await asyncio.sleep(max(0, delay))
