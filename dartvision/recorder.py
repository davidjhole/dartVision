"""Save every throw (before/after frame from each camera) so detection can be
re-run and improved later without throwing again."""
import glob
import json
import os
import shutil
import time

import cv2


class Recorder:
    def __init__(self, root="recordings", calib_folder="calib"):
        self.dir = os.path.join(root, time.strftime("session_%Y%m%d_%H%M%S"))
        os.makedirs(self.dir, exist_ok=True)
        if os.path.isdir(calib_folder):
            shutil.copytree(calib_folder, os.path.join(self.dir, "calib"), dirs_exist_ok=True)
        self.n = 0

    def save(self, before, after, event):
        d = os.path.join(self.dir, f"throw_{self.n:04d}")
        os.makedirs(d, exist_ok=True)
        for name in after:
            cv2.imwrite(os.path.join(d, f"{name}_before.png"), before[name])
            cv2.imwrite(os.path.join(d, f"{name}_after.png"), after[name])
        meta = {k: v for k, v in event.items() if k not in ("before_raw",)}
        meta["time"] = time.strftime("%H:%M:%S")
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(meta, f, indent=1, default=float)
        self.n += 1
        return d


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
