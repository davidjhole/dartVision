"""Keeps the last few hundred lines the program printed (and any errors), so the window and the
phone page can show them: an info line at the bottom and a log panel. Everything still goes to the
terminal as before. Standard library only.
"""
import collections
import re
import sys
import threading
import time
import traceback

MAX = 300
_lines = collections.deque(maxlen=MAX)        # (time, level, text)
_lock = threading.Lock()
_count = 0                                    # goes up with every line (lets callers spot changes)

_ERR = re.compile(r"error|exception|traceback|failed|couldn't|could not|crash", re.I)
_WARN = re.compile(r"warn|no picture|not started|not updating|skipped|not calibrated|didn't|bust", re.I)


def level_of(text, stream="out"):
    if _ERR.search(text):
        return "error"
    if stream == "err" or _WARN.search(text):     # stderr is mostly library warnings
        return "warn"
    return "info"


def add(text, level=None, stream="out"):
    global _count
    text = text.rstrip()
    if not text.strip():
        return
    with _lock:
        for line in text.splitlines():
            if line.strip():
                _lines.append((time.time(), level or level_of(line, stream), line))
                _count += 1


def lines(n=MAX):
    with _lock:
        return list(_lines)[-n:]


def last(min_level="info"):
    """The newest line at or above min_level, or None."""
    order = {"info": 0, "warn": 1, "error": 2}
    with _lock:
        for ln in reversed(_lines):
            if order[ln[1]] >= order[min_level]:
                return ln
    return None


def count():
    return _count


def clear():
    global _count
    with _lock:
        _lines.clear()
        _count = 0


class _Tee:
    """Passes writes through to the real stream and records whole lines."""

    def __init__(self, stream, name):
        self._s, self._name, self._buf = stream, name, ""

    def write(self, s):
        try:
            n = self._s.write(s)
        except Exception:   # noqa - a closed terminal mustn't stop the game
            n = len(s)
        self._buf += s
        if "\n" in self._buf:
            done, self._buf = self._buf.rsplit("\n", 1)
            add(done, stream=self._name)
        return n

    def flush(self):
        try:
            self._s.flush()
        except Exception:   # noqa
            pass

    def __getattr__(self, k):
        return getattr(self._s, k)


_installed = False


def install():
    """Start recording: stdout, stderr, and uncaught errors (main thread and background threads)."""
    global _installed
    if _installed:
        return
    _installed = True
    sys.stdout = _Tee(sys.stdout, "out")
    sys.stderr = _Tee(sys.stderr, "err")
    old_hook = threading.excepthook

    def thread_hook(args):
        add(f"error in background thread {args.thread.name if args.thread else ''}: "
            f"{args.exc_type.__name__}: {args.exc_value}", "error")
        old_hook(args)
    threading.excepthook = thread_hook


def error(msg, exc=None):
    """Record an error that was caught (and print it, so it's in the terminal too)."""
    if exc is not None:
        msg = f"{msg}: {type(exc).__name__}: {exc}"
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        sys.__stderr__.write(tb)
    try:
        sys.__stdout__.write(msg + "\n")
        sys.__stdout__.flush()
    except Exception:   # noqa
        pass
    add(msg, "error")


def for_web(n=120):
    return [[round(t), lv, s] for t, lv, s in lines(n)]
