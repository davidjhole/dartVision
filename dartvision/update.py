"""Check GitHub for a newer release and install it.

- If the program was installed with `git clone`, updating is a `git pull`.
- Otherwise the release zip is downloaded and unpacked over the program,
  keeping your own files (config.yaml, calib/, recordings/, .venv/).
Your settings, calibrations and recordings are never touched.
"""
import base64
import io
import json
import os
import re
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


def _get(url, timeout):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _version_on_branch(repo, branch, timeout):
    """Read __version__ straight from dartvision/__init__.py on GitHub."""
    try:   # API first: not cached, so a fresh push shows up straight away
        d = json.loads(_get(f"https://api.github.com/repos/{repo}/contents/dartvision/__init__.py?ref={branch}", timeout))
        src = base64.b64decode(d["content"]).decode("utf-8", "replace")
    except Exception:   # rate limited etc. - raw file (may lag a few minutes behind)
        src = _get(f"https://raw.githubusercontent.com/{repo}/{branch}/dartvision/__init__.py", timeout)
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', src)
    return m.group(1) if m else None


def _changelog_entry(repo, branch, version, timeout):
    """The section for `version` from CHANGELOG.md, if there is one."""
    try:
        text = _get(f"https://raw.githubusercontent.com/{repo}/{branch}/CHANGELOG.md", timeout)
    except Exception:
        return ""
    m = re.search(rf"^## v?{re.escape(version)}\b.*?(?=^## |\Z)", text, re.M | re.S)
    return m.group(0).strip() if m else ""


def check(repo, timeout=4, branch="main"):
    """Returns {'latest', 'newer', 'notes', 'url', 'zip'} or {'error': ...}.

    Uses the latest GitHub release if there is one; otherwise the version number
    in the code on the main branch (so a plain push is enough to ship an update)."""
    if not repo or "/" not in repo:
        return {"error": "no GitHub repo set (update: repo: in config.yaml)"}
    try:
        d = json.loads(_get(f"https://api.github.com/repos/{repo}/releases/latest", timeout))
        tag = d.get("tag_name", "")
        if tag:
            return {"latest": tag, "newer": _ver(tag) > _ver(__version__), "notes": (d.get("body") or "").strip(),
                    "url": d.get("html_url"), "zip": d.get("zipball_url")}
    except Exception:
        pass  # no releases yet, offline or rate limited - try the branch
    try:
        v = _version_on_branch(repo, branch, timeout)
    except Exception as e:
        return {"error": str(e)}
    if not v:
        return {"error": "couldn't find a version number on GitHub"}
    return {"latest": f"v{v}", "newer": _ver(v) > _ver(__version__),
            "notes": _changelog_entry(repo, branch, v, timeout),
            "url": f"https://github.com/{repo}", "zip": f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"}


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
