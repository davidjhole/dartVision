"""Which physical camera is behind each OpenCV index.

OpenCV only numbers cameras (0, 1, 2 ...), and the numbers change when a camera is unplugged,
switched off on a hub or the computer restarts - so "index 0" can turn into a different camera,
or the laptop's own webcam. This module gives each camera a stable id and a name:

* macOS: the AVFoundation uniqueID (tied to the USB port) and the device name. OpenCV numbers
  AVFoundation devices in uniqueID order, so we can work out the index from the id.
  Needs the small pyobjc AVFoundation package (installed from requirements.txt on a Mac).
* Linux / Raspberry Pi: the /dev/v4l/by-path link (tied to the USB port) and the sysfs name.
* Windows: not available - cameras are used by index as before.

Every function returns empty results when the information isn't available, so callers can
always fall back to plain indexes.
"""
import glob
import os
import platform

SYSTEM = platform.system()

# names of cameras that are part of the computer or a phone, never one of ours
_BUILTIN_WORDS = ("facetime", "iphone", "ipad", "desk view", "continuity", "integrated", "built-in")


def _mac_devices():
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeMuxed, AVMediaTypeVideo
    except Exception:
        return None
    devs = list(AVCaptureDevice.devicesWithMediaType_(AVMediaTypeVideo) or []) + \
        list(AVCaptureDevice.devicesWithMediaType_(AVMediaTypeMuxed) or [])
    devs.sort(key=lambda d: str(d.uniqueID()))     # the same order OpenCV uses
    out = []
    for i, d in enumerate(devs):
        try:
            dtype = str(d.deviceType())
        except Exception:
            dtype = ""
        name = str(d.localizedName())
        builtin = "BuiltIn" in dtype or any(w in name.lower() for w in _BUILTIN_WORDS)
        out.append({"index": i, "id": str(d.uniqueID()), "name": name, "builtin": builtin})
    return out


def _linux_devices():
    out = []
    links = {}
    for link in glob.glob("/dev/v4l/by-path/*"):
        try:
            links[os.path.realpath(link)] = link
        except OSError:
            pass
    for dev in sorted(glob.glob("/dev/video*")):
        try:
            idx = int(dev[len("/dev/video"):])
        except ValueError:
            continue
        name = ""
        try:
            with open(f"/sys/class/video4linux/video{idx}/name") as f:
                name = f.read().strip()
        except OSError:
            pass
        link = links.get(os.path.realpath(dev))
        out.append({"index": idx, "id": link, "name": name,
                    "builtin": any(w in name.lower() for w in _BUILTIN_WORDS)})
    return out


def list_devices():
    """[{index, id, name, builtin}] for every video device, or [] if not available here."""
    if SYSTEM == "Darwin":
        return _mac_devices() or []
    if SYSTEM == "Linux":
        return _linux_devices()
    return []


def describe(index, devices=None):
    devices = list_devices() if devices is None else devices
    for d in devices:
        if d["index"] == index:
            return d
    return None


def index_for_id(dev_id, devices=None):
    """Current OpenCV index of the camera with this stable id, or None."""
    if not dev_id:
        return None
    devices = list_devices() if devices is None else devices
    for d in devices:
        if d["id"] == dev_id:
            return d["index"]
    return None
