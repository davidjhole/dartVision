"""Save every throw (before/after frame from each camera) so detection can be
re-run and improved later without throwing again."""
import glob
import json
import os
import queue
import shutil
import threading
import time

import cv2


PNG_FAST = [cv2.IMWRITE_PNG_COMPRESSION, 1]     # bigger files, but several times quicker to write
JPG_GOOD = [cv2.IMWRITE_JPEG_QUALITY, 95]       # ~0.25 MB a picture instead of ~1.6 MB; re-running
                                                # detection on these scores the same as on PNGs


class Recorder:
    """meta.json is written straight away (labels are added to it later); the pictures are
    written on a background thread. Eight full-size PNGs per dart took a couple of seconds on a
    Raspberry Pi, and the score waited for them."""

    def __init__(self, root="recordings", calib_folder="calib", background=True, fmt="jpg", max_mb=2000):
        self.root = root
        self.fmt = "png" if str(fmt).lower() == "png" else "jpg"
        self.max_bytes = int(float(max_mb) * 1e6) if max_mb else 0
        self.dir = os.path.join(root, time.strftime("session_%Y%m%d_%H%M%S"))
        os.makedirs(self.dir, exist_ok=True)
        self.cleanup()
        if os.path.isdir(calib_folder):
            shutil.copytree(calib_folder, os.path.join(self.dir, "calib"), dirs_exist_ok=True)
        self.n = 0
        self.q = queue.Queue()
        self.background = background
        if background:
            threading.Thread(target=self._writer, daemon=True).start()

    def save(self, before, after, event):
        d = os.path.join(self.dir, f"throw_{self.n:04d}")
        os.makedirs(d, exist_ok=True)
        meta = {k: v for k, v in event.items() if k not in ("before_raw",)}
        meta["time"] = time.strftime("%H:%M:%S")
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(meta, f, indent=1, default=float)
        job = (d, dict(before), dict(after))       # the frames are copies: the game loop doesn't reuse them
        if self.background:
            if self.q.qsize() > 20:                # disk can't keep up: drop pictures, never the game
                print("recorder: falling behind, skipped saving the pictures for", os.path.basename(d))
            else:
                self.q.put(job)
        else:
            self._write(*job)
        self.n += 1
        return d

    def flush(self, timeout=10.0):
        """Wait (up to timeout s) for the pictures still being written."""
        t0 = time.time()
        while self.background and self.q.unfinished_tasks and time.time() - t0 < timeout:
            time.sleep(0.02)

    def _writer(self):
        while True:
            job = self.q.get()
            try:
                self._write(*job)
            except Exception as e:  # noqa - a full disk mustn't stop the game
                print("recorder: couldn't save the pictures:", e)
            finally:
                self.q.task_done()

    def _write(self, d, before, after):
        ext, params = (".png", PNG_FAST) if self.fmt == "png" else (".jpg", JPG_GOOD)
        for name in after:
            if name in before and before[name] is not None:
                cv2.imwrite(os.path.join(d, f"{name}_before{ext}"), before[name], params)
            cv2.imwrite(os.path.join(d, f"{name}_after{ext}"), after[name], params)
        if self.n % 10 == 0:
            self.cleanup()

    def cleanup(self):
        """Keep the recordings under max_mb: delete the oldest sessions first (then, if this
        session alone is too big, its oldest throws, keeping the last 20)."""
        if not self.max_bytes:
            return
        try:
            sessions = sorted(glob.glob(os.path.join(self.root, "session_*")))
            sizes = {d: _size(d) for d in sessions}
            total = sum(sizes.values())
            freed = []
            for d in sessions:
                if total <= self.max_bytes:
                    break
                if os.path.abspath(d) == os.path.abspath(self.dir):
                    continue
                shutil.rmtree(d, ignore_errors=True)
                total -= sizes[d]
                freed.append(os.path.basename(d))
            if total > self.max_bytes:
                for d in sorted(glob.glob(os.path.join(self.dir, "throw_*")))[:-20]:
                    if total <= self.max_bytes:
                        break
                    sz = _size(d)
                    shutil.rmtree(d, ignore_errors=True)
                    total -= sz
                    freed.append(f"{os.path.basename(self.dir)}/{os.path.basename(d)}")
            if freed:
                print(f"recorder: recordings over {self.max_bytes / 1e6:.0f} MB - deleted the oldest: "
                      + ", ".join(freed[:5]) + (f" and {len(freed) - 5} more" if len(freed) > 5 else ""))
        except Exception as e:  # noqa
            print("recorder: couldn't tidy up old recordings:", e)


def _size(path):
    t = 0
    for dp, _, files in os.walk(path):
        for f in files:
            try:
                t += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return t


def _pic(d, name):
    for ext in (".jpg", ".png"):
        p = os.path.join(d, name + ext)
        if os.path.exists(p):
            return cv2.imread(p)
    return None


def iter_throws(session):
    for d in sorted(glob.glob(os.path.join(session, "throw_*"))):
        with open(os.path.join(d, "meta.json")) as f:
            meta = json.load(f)
        cams = sorted({os.path.basename(p).rsplit("_", 1)[0] for p in glob.glob(os.path.join(d, "*_after.*"))})
        if not cams:
            continue                        # pictures not saved (recordings: unknown) or tidied away
        before = {c: _pic(d, f"{c}_before") for c in cams}
        after = {c: _pic(d, f"{c}_after") for c in cams}
        yield d, meta, before, after


def _meta(throw_dir):
    p = os.path.join(throw_dir, "meta.json")
    with open(p) as f:
        return p, json.load(f)


def _quiet_missing(fn):
    """Labelling a throw whose folder was tidied away (recording size limit) does nothing."""
    def wrap(throw_dir, *a, **k):
        try:
            return fn(throw_dir, *a, **k)
        except FileNotFoundError:
            return None
    wrap.__doc__ = fn.__doc__
    return wrap


@_quiet_missing
def set_label(throw_dir, label, source="manual"):
    """Store the true score for a throw. source: corrected / accepted / entered /
    undone (a false detection) / manual (from the label command)."""
    p, meta = _meta(throw_dir)
    meta["true_label"] = label
    meta["label_source"] = source
    with open(p, "w") as f:
        json.dump(meta, f, indent=1, default=float)


@_quiet_missing
def accept_if_unlabelled(throw_dir):
    """A dart nobody corrected before the turn ended is taken as correct."""
    p, meta = _meta(throw_dir)
    if "true_label" not in meta and meta.get("label"):
        set_label(throw_dir, meta["label"], "accepted")
