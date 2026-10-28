"""Check GitHub for a newer release and install it.

- If the program was installed with `git clone`, updating is a `git pull`.
- Otherwise the release zip is downloaded and unpacked over the program,
  keeping your own files (config.yaml, calib/, recordings/, .venv/).
Your settings, calibrations and recordings are never touched.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile

from . import __version__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP = {"config.yaml", "calib", "recordings", ".venv", "venv", ".git"}
UA = {"User-Agent": f"dartvision/{__version__}", "Accept": "application/vnd.github+json"}


def _ver(tag):
    """'v0.2.1' -> (0, 2, 1); anything unparsable sorts lowest."""
    parts = []
    for p in tag.lstrip("vV").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts + [0] * (3 - len(parts)))


def check(repo, timeout=4):
    """Returns {'latest', 'newer', 'notes', 'url', 'zip'} or {'error': ...}."""
    if not repo or "/" not in repo:
        return {"error": "no GitHub repo set (update: repo: in config.yaml)"}
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest", headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except Exception as e:  # offline, rate limited, no releases yet ...
        return {"error": str(e)}
    tag = d.get("tag_name", "")
    return {"latest": tag, "newer": _ver(tag) > _ver(__version__), "notes": (d.get("body") or "").strip(),
            "url": d.get("html_url"), "zip": d.get("zipball_url")}


def check_in_background(repo, callback):
    """Non-blocking startup check: callback(info) is called only if a newer version exists."""
    def run():
        info = check(repo)
        if info.get("newer"):
            callback(info)
    threading.Thread(target=run, daemon=True).start()


def _pip_install():
    req = os.path.join(ROOT, "requirements.txt")
    if os.path.exists(req):
        subprocess.call([sys.executable, "-m", "pip", "install", "-q", "-r", req])


def apply(info, log=print):
    """Install the release described by `info` (from check). Returns True on success."""
    if os.path.isdir(os.path.join(ROOT, ".git")) and shutil.which("git"):
        log("Updating with git pull ...")
        if subprocess.call(["git", "-C", ROOT, "pull", "--ff-only"]) != 0:
            log("git pull failed - you may have local code changes. Nothing was changed.")
            return False
        _pip_install()
        return True
    if not info.get("zip"):
        log("No download link for this release.")
        return False
    log(f"Downloading {info['latest']} ...")
    req = urllib.request.Request(info["zip"], headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        top = os.path.join(tmp, os.listdir(tmp)[0])   # GitHub zips have one top folder
        for name in os.listdir(top):
            if name in KEEP:
                continue
            src, dst = os.path.join(top, name), os.path.join(ROOT, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
    _pip_install()
    log(f"Updated to {info['latest']}. Restart dartvision to use it.")
    return True
