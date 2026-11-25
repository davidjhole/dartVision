"""How the computer itself is doing: CPU temperature, throttling / under-voltage (Raspberry Pi),
CPU load, memory and disk. A background thread looks every few seconds and writes a "health:" line
to the log every health.log_every_min minutes, and straight away when something changes (it gets
hotter or cooler by a step, the Pi starts or stops slowing itself down, power dips, memory or disk
runs low).

    health: 78.4°C hot, CPU 1.5/2.4 GHz, load 1.20 (4 cores), CPU 34% (dartvision 30%), memory 410/3796 MB,
            disk 21.0 GB free, fan 3200 rpm | Pi: OK now; since boot: hit the soft temperature limit (0x80000)

Also builds the text report the Settings page downloads / copies (report()). Standard library only;
anything a computer doesn't have (no vcgencmd on a Mac, no fan) is just left out.
"""
import collections
import glob
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time

from . import logbuf

# vcgencmd get_throttled bits: (bit, short words for the log)
NOW_BITS = [(0, "under-voltage (power supply too weak)"), (1, "CPU speed capped"),
            (2, "throttled (CPU slowed down)"), (3, "soft temperature limit (CPU slowed to cool down)")]
SINCE_BITS = [(16, "under-voltage"), (17, "CPU speed capped"), (18, "throttled"),
              (19, "hit the soft temperature limit")]
TEMP_BANDS = [(80, "very hot"), (70, "hot"), (60, "warm"), (-99, "cool")]
HYST = 2.0                      # °C past a band edge before it counts as a change (no flapping)


def decode_throttled(value):
    """0x80000 -> ([], ['hit the soft temperature limit']): (problems now, problems since boot)."""
    if value is None:
        return [], []
    return ([w for b, w in NOW_BITS if value >> b & 1], [w for b, w in SINCE_BITS if value >> b & 1])


def describe_throttled(value):
    if value is None:
        return ""
    now, since = decode_throttled(value)
    out = "Pi: " + ("NOW " + ", ".join(now) if now else "OK now")
    if since:
        out += "; since boot: " + ", ".join(since)
    return out + f" (0x{value:x})"


def temp_band(t, prev=None):
    """'cool' / 'warm' / 'hot' / 'very hot'. With the previous band, a temperature just past an
    edge keeps the old band until it's HYST degrees past it."""
    if t is None:
        return None
    band = next(name for edge, name in TEMP_BANDS if t >= edge)
    if prev and prev != band:
        edges = {name: edge for edge, name in TEMP_BANDS}
        lo = edges[prev]
        hi = min([e for e, _ in TEMP_BANDS if e > lo], default=999)
        if lo - HYST <= t < hi + HYST:
            return prev
    return band


# ------------------------------------------------------------------ reading the machine
def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def read_temp():
    v = _read("/sys/class/thermal/thermal_zone0/temp")
    try:
        return round(int(v) / 1000, 1) if v else None
    except ValueError:
        return None


def read_throttled():
    v = _read("/sys/devices/platform/soc/soc:firmware/get_throttled")     # newer Pi kernels: no subprocess
    if v:
        try:
            return int(v, 16)
        except ValueError:
            pass
    if not shutil.which("vcgencmd"):
        return None
    try:
        r = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=3)
        m = re.search(r"0x([0-9a-fA-F]+)", r.stdout)
        return int(m.group(1), 16) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def read_freq():
    cur = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    top = _read("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    try:
        return (int(cur) / 1e6 if cur else None), (int(top) / 1e6 if top else None)
    except ValueError:
        return None, None


def read_fan():
    for p in glob.glob("/sys/devices/platform/cooling_fan/hwmon/hwmon*/fan1_input"):
        v = _read(p)
        if v and v.isdigit():
            return int(v)
    return None


def read_mem():
    """(used MB, total MB) of the whole computer, and this program's own MB."""
    info = {}
    for ln in (_read("/proc/meminfo") or "").splitlines():
        k, _, rest = ln.partition(":")
        try:
            info[k] = int(rest.split()[0]) / 1024
        except (IndexError, ValueError):
            pass
    used = total = None
    if "MemTotal" in info and "MemAvailable" in info:
        total, used = info["MemTotal"], info["MemTotal"] - info["MemAvailable"]
    own = None
    for ln in (_read("/proc/self/status") or "").splitlines():
        if ln.startswith("VmRSS:"):
            own = int(ln.split()[1]) / 1024
    return used, total, own


def read_cpu_ticks():
    ln = (_read("/proc/stat") or "").split("\n", 1)[0].split()
    if not ln or ln[0] != "cpu":
        return None
    v = [int(x) for x in ln[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v), idle


def read_model():
    m = _read("/proc/device-tree/model")
    if m:
        return m.strip("\x00")
    return platform.platform()


def read_os():
    for ln in (_read("/etc/os-release") or "").splitlines():
        if ln.startswith("PRETTY_NAME="):
            return ln.split("=", 1)[1].strip('"')
    return platform.system() + " " + platform.release()


def read_uptime():
    v = _read("/proc/uptime")
    try:
        return float(v.split()[0]) if v else None
    except ValueError:
        return None


def _dur(s):
    if s is None:
        return "?"
    s = int(s)
    d, h, m = s // 86400, s // 3600 % 24, s // 60 % 60
    return (f"{d}d " if d else "") + (f"{h}h " if d or h else "") + f"{m}m"


# ------------------------------------------------------------------ the monitor
class Monitor:
    def __init__(self, every_s=5.0, log_every_min=10, disk_path=".", emit=None):
        self.every_s = every_s
        self.log_every_s = max(60.0, float(log_every_min) * 60)
        self.disk_path = disk_path
        self._emit = emit or _emit
        self.now = {}                       # the latest sample (what the web page shows)
        self.history = collections.deque(maxlen=24 * 60)    # one sample a minute for a day
        self.temp_max = None
        self.started = time.time()
        self._lock = threading.Lock()
        self._prev_ticks = read_cpu_ticks()
        self._prev_own = (time.monotonic(), _own_cpu())
        self._band = None
        self._throttled = None
        self._low_mem = self._low_disk = False
        self._last_log = 0.0
        self._last_hist = 0.0
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name="health", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        self._stop.wait(1.0)        # a first CPU % needs a moment between two readings
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:      # noqa - watching the health must never stop the game
                logbuf.error("health check failed", e)
                self._stop.wait(60)
            self._stop.wait(self.every_s)

    def sample(self):
        s = {"t": time.time(), "temp": read_temp(), "throttled": read_throttled(), "fan": read_fan()}
        s["freq"], s["freq_max"] = read_freq()
        try:
            la = os.getloadavg()
            s["load"] = round(la[0], 2)
        except (OSError, AttributeError):
            s["load"] = None
        s["cores"] = os.cpu_count() or 1
        ticks = read_cpu_ticks()
        s["cpu"] = None
        if ticks and self._prev_ticks and ticks[0] > self._prev_ticks[0]:
            dt, di = ticks[0] - self._prev_ticks[0], ticks[1] - self._prev_ticks[1]
            s["cpu"] = round(100 * (1 - di / dt))
        self._prev_ticks = ticks
        mono, own = time.monotonic(), _own_cpu()
        pt, po = self._prev_own
        # this program, as % of the whole computer (all cores) - same scale as "cpu"
        s["own_cpu"] = round(100 * (own - po) / max(1e-6, mono - pt) / s["cores"]) if mono > pt else None
        self._prev_own = (mono, own)
        s["mem_used"], s["mem_total"], s["own_mem"] = read_mem()
        try:
            s["disk_free"] = round(shutil.disk_usage(self.disk_path).free / 1e9, 1)
        except OSError:
            s["disk_free"] = None
        return s

    def tick(self):
        s = self.sample()
        reasons = []
        band = temp_band(s["temp"], self._band)
        if band and self._band and band != self._band:
            reasons.append(f"temperature now {band}")
        self._band = band
        th = s["throttled"]
        if th is not None and self._throttled is not None and th != self._throttled:
            was_now, was_since = decode_throttled(self._throttled)
            now, since = decode_throttled(th)
            new = [w for w in now if w not in was_now] + [f"since boot: {w}" for w in since if w not in was_since]
            gone = [w for w in was_now if w not in now]
            if new:
                reasons.append("new: " + ", ".join(new))
            if gone:
                reasons.append("stopped: " + ", ".join(gone))
        self._throttled = th
        low_mem = bool(s["mem_total"] and s["mem_used"] / s["mem_total"] > 0.9)
        if low_mem != self._low_mem:
            reasons.append("memory nearly full" if low_mem else "memory OK again")
        self._low_mem = low_mem
        low_disk = s["disk_free"] is not None and s["disk_free"] < 1.0
        if low_disk != self._low_disk:
            reasons.append("disk nearly full" if low_disk else "disk space OK again")
        self._low_disk = low_disk
        with self._lock:
            self.now = s
            if s["temp"] is not None:
                self.temp_max = max(self.temp_max or s["temp"], s["temp"])
            if s["t"] - self._last_hist >= 60:
                self._last_hist = s["t"]
                self.history.append(s)
        first = self._last_log == 0
        if first or reasons or s["t"] - self._last_log >= self.log_every_s:
            self._last_log = s["t"]
            why = "started" if first else "; ".join(reasons) if reasons else ""
            self._emit(self.line(s) + (f"  [{why}]" if why else ""), self.level(s))
        return s

    def line(self, s=None):
        s = s if s is not None else self.now
        if not s:
            return "health: not measured yet"
        bits = []
        if s.get("temp") is not None:
            bits.append(f"{s['temp']:.1f}°C {temp_band(s['temp'], self._band)}")
        if s.get("freq"):
            bits.append(f"CPU {s['freq']:.1f}" + (f"/{s['freq_max']:.1f}" if s.get("freq_max") else "") + " GHz")
        if s.get("load") is not None:
            bits.append(f"load {s['load']:.2f} ({s['cores']} cores)")
        if s.get("cpu") is not None:
            bits.append(f"CPU {s['cpu']}%" + (f" (dartvision {s['own_cpu']}%)" if s.get("own_cpu") is not None else ""))
        if s.get("mem_total"):
            bits.append(f"memory {s['mem_used']:.0f}/{s['mem_total']:.0f} MB"
                        + (f" (dartvision {s['own_mem']:.0f})" if s.get("own_mem") else ""))
        if s.get("disk_free") is not None:
            bits.append(f"disk {s['disk_free']:.1f} GB free")
        if s.get("fan") is not None:
            bits.append(f"fan {s['fan']} rpm")
        out = "health: " + ", ".join(bits)
        th = describe_throttled(s.get("throttled"))
        return out + (f" | {th}" if th else "")

    @staticmethod
    def level(s):
        now, since = decode_throttled(s.get("throttled"))
        if now or "under-voltage" in since or (s.get("temp") or 0) >= 80:
            return "warn"
        if s.get("disk_free") is not None and s["disk_free"] < 1.0:
            return "warn"
        return "info"

    def for_web(self):
        with self._lock:
            s = dict(self.now)
        if not s:
            return None
        now, since = decode_throttled(s.get("throttled"))
        return {"temp": s.get("temp"), "temp_max": self.temp_max, "band": temp_band(s.get("temp"), self._band),
                "freq": s.get("freq"), "freq_max": s.get("freq_max"), "load": s.get("load"),
                "cores": s.get("cores"), "cpu": s.get("cpu"), "own_cpu": s.get("own_cpu"),
                "mem_used": round(s["mem_used"]) if s.get("mem_used") else None,
                "mem_total": round(s["mem_total"]) if s.get("mem_total") else None,
                "disk_free": s.get("disk_free"), "fan": s.get("fan"),
                "throttled": None if s.get("throttled") is None else f"0x{s['throttled']:x}",
                "now": now, "since": since, "level": self.level(s),
                "up": _dur(time.time() - self.started)}

    def history_lines(self, every_min=5, hours=6):
        with self._lock:
            h = list(self.history)
        cut = time.time() - hours * 3600
        out, last = [], 0
        for s in h:
            if s["t"] < cut or s["t"] - last < every_min * 60 - 5:
                continue
            last = s["t"]
            th = "" if s.get("throttled") is None else f"0x{s['throttled']:x}"
            temp = "" if s.get("temp") is None else f"{s['temp']:.1f}°C"
            cpu = "" if s.get("cpu") is None else s["cpu"]
            load = "" if s.get("load") is None else s["load"]
            out.append(f"{time.strftime('%H:%M', time.localtime(s['t']))}  {temp:>7}  CPU {cpu:>3}%  load {load:<5}  {th}")
        return out


def _own_cpu():
    t = os.times()
    return t.user + t.system


def _emit(text, level):
    """Print (so it reaches the terminal / journal) and record with the given level."""
    try:
        sys.__stdout__.write(text + "\n")
        sys.__stdout__.flush()
    except Exception:   # noqa
        pass
    logbuf.add(text, level)


# ------------------------------------------------------------------ the shareable report
_TOTAL = re.compile(r"= ([\d.]+) s from landing to score")


def timing_summary(lines):
    """From the "timing:" lines: how many darts and how long from landing to score."""
    tot = sorted(float(m.group(1)) for _, _, s in lines if s.startswith("timing: dart")
                 for m in [_TOTAL.search(s)] if m)
    if not tot:
        return "no darts timed yet"
    med = tot[len(tot) // 2]
    return f"{len(tot)} darts: landing to score median {med:.2f} s, fastest {tot[0]:.2f} s, slowest {tot[-1]:.2f} s"


def config_summary(cfg, calibrated=()):
    if not cfg:
        return []
    cams = cfg.get("cameras") or []
    out = [f"cameras: {len(cams)} - " + (", ".join(
        f"{c.get('name')} (index {c.get('index')}, rotate {c.get('rotate', 0)}"
        + (", calibrated" if c.get("name") in calibrated else ", NOT calibrated") + ")" for c in cams) or "none"),
        f"picture: {cfg.get('width')}x{cfg.get('height')} at {cfg.get('fps')} fps, exposure {cfg.get('exposure')}",
        "detection: " + ", ".join(f"{k} {v}" for k, v in (cfg.get("detection") or {}).items())]
    v = cfg.get("voice") or {}
    out.append(f"voice: {'on' if v.get('enabled') else 'off'}, output {v.get('output')}, engine {v.get('engine')}")
    out.append(f"lights: {(cfg.get('lights') or {}).get('type', 'none')}")
    u = cfg.get("update") or {}
    out.append(f"update: auto {u.get('auto')}, branch {u.get('branch')}")
    return out


def report(version="", cfg=None, calibrated=(), monitor=None, extra=None, max_lines=None):
    """One plain-text bundle to download or paste into a chat: what's running, the settings, the
    computer's health and the log."""
    lines = logbuf.lines()
    if max_lines:
        lines = lines[-max_lines:]
    up = read_uptime()
    out = [f"dartvision report - {time.strftime('%Y-%m-%d %H:%M:%S')}",
           f"version: {version}",
           f"computer: {read_model()} | {read_os()} | Python {platform.python_version()}",
           f"computer up {_dur(up)}" + (f", dartvision up {_dur(time.time() - monitor.started)}" if monitor else "")]
    for k, v in (extra or {}).items():
        out.append(f"{k}: {v}")
    out += ["", "== Health now"]
    if monitor:
        s = monitor.now
        out.append(monitor.line(s) if s else monitor.line(monitor.sample()))
        if monitor.temp_max is not None:
            out.append(f"hottest since dartvision started: {monitor.temp_max:.1f}°C")
        th = (s or {}).get("throttled")
        if th is not None:
            now, since = decode_throttled(th)
            out.append(f"throttled=0x{th:x}: now: {', '.join(now) or 'nothing'}; since boot: {', '.join(since) or 'nothing'}")
        hist = monitor.history_lines()
        if hist:
            out += ["", "== Health every 5 minutes (last 6 hours)"] + hist
    else:
        out.append("not watched")
    out += ["", "== Speed", timing_summary(logbuf.lines())]
    out += ["", "== Settings"] + config_summary(cfg, calibrated)
    out += ["", f"== Log ({len(lines)} lines, oldest first)"]
    out += [f"{time.strftime('%H:%M:%S', time.localtime(t))} {lv[0].upper()} {s}" for t, lv, s in lines]
    return "\n".join(out) + "\n"
