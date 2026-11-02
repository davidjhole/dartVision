"""Settings file (config.yaml) and per-camera calibration files (calib/<name>.json)."""
import json
import os
import time

import numpy as np
import yaml

DEFAULT = {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "cameras": [],          # [{name: cam1, index: 0, rotate: 0}]
    "exposure": None,       # None = auto. Otherwise a camera-specific number.
    "detection": {
        "diff_threshold": 28,      # grey-level change counted as "something moved"
        "motion_on": 0.0012,       # fraction of pixels moving to start an event
        "motion_off": 0.0005,      # ... and to call it settled again
        "settle_frames": 6,        # quiet frames before we look at the result
        "min_dart_px": 120,        # smallest believable dart blob (pixels, full res)
        "max_dart_px": 25000,      # bigger than this = hand / takeout / lighting
        "fuse_tolerance_mm": 12,   # cameras agreeing within this are averaged
    },
    "record_dir": "recordings",
    "update": {
        "repo": "davidjhole/dartVision",  # GitHub "owner/name" to check for new releases
        "check_on_start": True,
    },
}


def load_config(path="config.yaml"):
    cfg = json.loads(json.dumps(DEFAULT))
    if os.path.exists(path):
        with open(path) as f:
            user = yaml.safe_load(f) or {}
        nested = {k: user.pop(k, {}) or {} for k in ("detection", "update")}
        cfg.update(user)
        for k, v in nested.items():
            cfg[k].update(v)
    return cfg


def save_config(cfg, path="config.yaml"):
    with open(path, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)


def calib_path(name, folder="calib"):
    return os.path.join(folder, f"{name}.json")


def save_calibration(name, image_points, board_points, H, image_size, folder="calib"):
    os.makedirs(folder, exist_ok=True)
    data = {
        "camera": name,
        "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
        "image_size": list(image_size),
        "image_points": [list(map(float, p)) for p in image_points],
        "board_points_mm": [list(map(float, p)) for p in board_points],
        "H_board_to_image": np.asarray(H).tolist(),
    }
    with open(calib_path(name, folder), "w") as f:
        json.dump(data, f, indent=2)


def load_calibration(name, folder="calib"):
    p = calib_path(name, folder)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        d = json.load(f)
    H = np.array(d["H_board_to_image"], dtype=np.float64)
    d["H"] = H
    d["H_inv"] = np.linalg.inv(H)
    return d
