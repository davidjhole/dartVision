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


class Recorder:
    """meta.json is written straight away (labels are added to it later); the pictures are
    written on a background thread. Eight full-size PNGs per dart took a couple of seconds on a
    Raspberry Pi, and the score waited for them."""

    def __init__(self, root="recordings", calib_folder="calib", background=True):
        self.dir = os.path.join(root, time.strftime("session_%Y%m%d_%H%M%S"))
        os.makedirs(self.dir, exist_ok=True)
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

    @staticmethod
    def _write(d, before, after):
        for name in after:
            if name in before and before[name] is not None:
                cv2.imwrite(os.path.join(d, f"{name}_before.png"), before[name], PNG_FAST)
            cv2.imwrite(os.path.join(d, f"{name}_after.png"), after[name], PNG_FAST)


def iter_throws(session):
    for d in sorted(glob.glob(os.path.join(session, "throw_*"))):
        with open(os.path.join(d, "meta.json")) as f:
            meta = json.load(f)
        cams = sorted({os.path.basename(p).rsplit("_", 1)[0] for p in glob.glob(os.path.join(d, "*_after.png"))})
        before = {c: cv2.imread(os.path.join(d, f"{c}_before.png")) for c in cams}
        after = {c: cv2.imread(os.path.join(d, f"{c}_after.png")) for c in cams}
        yield d, meta, before, after


def _meta(throw_dir):
    p = os.path.join(throw_dir, "meta.json")
    with open(p) as f:
        return p, json.load(f)


def set_label(throw_dir, label, source="manual"):
    """Store the true score for a throw. source: corrected / accepted / entered /
    undone (a false detection) / manual (from the label command)."""
    p, meta = _meta(throw_dir)
    meta["true_label"] = label
    meta["label_source"] = source
    with open(p, "w") as f:
        json.dump(meta, f, indent=1, default=float)


def accept_if_unlabelled(throw_dir):
    """A dart nobody corrected before the turn ended is taken as correct."""
    p, meta = _meta(throw_dir)
    if "true_label" not in meta and meta.get("label"):
        set_label(throw_dir, meta["label"], "accepted")
