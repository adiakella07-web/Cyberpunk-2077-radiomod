import collections
import time

_lines = collections.deque(maxlen=80)


def log(msg: str):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    _lines.append(line)
    print(line, flush=True)


def recent(n=20):
    return list(_lines)[-n:]
