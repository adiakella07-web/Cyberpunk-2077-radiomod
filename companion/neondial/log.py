import collections
import re
import time

_lines = collections.deque(maxlen=80)

# Nothing that identifies an account or could be used to log in may ever reach the activity log, the log file or the
# in-game panel (people screenshot those). Redact before storing or printing.
_AUTH = re.compile(r"(?i)\b(authenticated|logged in|login|signed in|credentials?)\b[^,;\n]*?\b(as|for|user(name)?)\b[:= ]+\S+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_URL = re.compile(r"(?i)\b(https?|spotify|file)://[^\s>]+|\bspotify:(user|playlist|track|album|artist):[^\s>]+")
_TOKEN = re.compile(r"\b[A-Za-z0-9_\-]{28,}\b")
_KV = re.compile(r"(?i)\b(token|secret|password|passwd|cookie|authorization|bearer|code|key)\b\s*[:=]\s*\S+")
_HOME = re.compile(r"(?i)[A-Z]:\\Users\\[^\\]+")


def redact(msg: str) -> str:
    msg = _AUTH.sub(lambda m: m.group(1) + " (account hidden)", msg)
    msg = _KV.sub(lambda m: m.group(1) + "=<hidden>", msg)
    msg = _EMAIL.sub("<email>", msg)
    msg = _URL.sub("<link>", msg)
    msg = _TOKEN.sub("<hidden>", msg)
    msg = _HOME.sub(r"<user folder>", msg)
    return msg


def log(msg: str):
    line = f"{time.strftime('%H:%M:%S')} {redact(str(msg))}"
    _lines.append(line)
    print(line, flush=True)


def recent(n=20):
    return list(_lines)[-n:]


class RedactingFile:
    """Wraps the log file so even tracebacks or stray prints can't write account details or the Windows user name."""

    def __init__(self, f):
        self._f = f

    def write(self, text):
        return self._f.write(redact(text))

    def flush(self):
        self._f.flush()

    def isatty(self):
        return False
