"""Test-tone provider: lets you verify the in-game station works before touching Spotify."""
import array
import asyncio
import math

from ..audio import RATE, FRAME_BYTES
from . import Provider

NOTES = [220.0, 261.63, 329.63, 392.0, 329.63, 261.63]


class DemoProvider(Provider):
    name = "demo"

    def __init__(self, cfg, engine):
        self.engine = engine
        self.playing = False
        self._n = 0
        self._task = None

    async def start(self):
        self._task = asyncio.create_task(self._loop())

    async def play(self):
        self.playing = True

    async def pause(self):
        self.playing = False
        self.engine.flush()

    def _chunk(self):
        frames = FRAME_BYTES // 4
        out = array.array("h")
        for i in range(frames):
            n = self._n + i
            t = n / RATE
            note = NOTES[int(t / 0.25) % len(NOTES)]
            env = 1.0 - ((t % 0.25) / 0.25) * 0.8
            v = (math.sin(2 * math.pi * note * t) + 0.4 * math.sin(2 * math.pi * note * 2 * t)) * env
            s = int(v * 0.25 * 32767)
            out.append(s)
            out.append(s)
        self._n += frames
        return out.tobytes()

    async def _loop(self):
        while True:
            if self.playing and self.engine.room():
                self.engine.feed(self._chunk())
            await asyncio.sleep(0.02)

    def state(self):
        return {"now": {"title": "Test tone", "artist": "Neon Dial demo", "playing": self.playing}}
