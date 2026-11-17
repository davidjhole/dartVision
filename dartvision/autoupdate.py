"""Update on start (git installs): fetch main, fast-forward if it's safe, restart on the new code.

Made for a Pi with no screen, where nobody is there to answer a prompt:
- offline / GitHub slow: start the version that's here (fetch has a short timeout)
- local code changes, another branch checked out, or history that doesn't fast-forward: skip, say why
- only ever runs before the game starts, never in the middle of one
- the new code is tried in a separate Python first (imports + `version`); if that fails, or the
  restarted program crashes before the game loop is running, it goes back to the commit it had and
  remembers the bad one, so it doesn't update to it again (a later push is tried as normal)
Your config.yaml, calib/ and recordings/ are untracked, so git never touches them.
Standard library only.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = ".dartvision_update.json"           # in ROOT, git-ignored
ENV_UPDATED = "DARTVISION_UPDATED_FROM"           # set on the restart after an update
SMOKE = ("import dartvision.__main__, dartvision.games, dartvision.menu, dartvision.web, "
         "dartvision.update, dartvision.autoupdate")


def _git(root, *args, timeout=15):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo", LC_ALL="C")
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=timeout, env=env)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _load(root):
    try:
        with open(os.path.join(root, STATE_FILE)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(root, st):
    try:
        with open(os.path.join(root, STATE_FILE), "w") as f:
            json.dump(st, f)
    except OSError:
        pass


def _short(root, ref):
    code, out, _ = _git(root, "log", "-1", "--format=%h %s", ref)
    return out if code == 0 else ref[:7]


def _pip_install(root):
    req = os.path.join(root, "requirements.txt")
    if os.path.exists(req):
        subprocess.call([sys.executable, "-m", "pip", "install", "-q", "-r", req])


def _smoke_test(root):
    """Can the new code at least start? Run in a fresh Python so this process isn't affected."""
    env = dict(os.environ, PYTHONPATH=root + os.pathsep + os.environ.get("PYTHONPATH", ""))
    env.pop(ENV_UPDATED, None)
    try:
        r = subprocess.run([sys.executable, "-c", SMOKE], cwd=root, env=env, capture_output=True, text=True,
                           timeout=120)
        if r.returncode:
            return False, (r.stderr or r.stdout).strip().splitlines()[-1:] or ["failed"]
        r = subprocess.run([sys.executable, "-m", "dartvision", "version"], cwd=root, env=env,
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stderr or r.stdout).strip().splitlines()[-1:]
    except (OSError, subprocess.SubprocessError) as e:
        return False, [str(e)]


def update(root=ROOT, branch="main", remote="origin", timeout=15, log=print, pip=_pip_install, smoke=_smoke_test):
    """Bring the checkout up to date if it's safe. Returns (result, message).

    result: 'updated' (restart needed), 'up_to_date', 'skipped', 'offline', 'rolled_back' or 'error'.
    """
    try:
        if not os.path.isdir(os.path.join(root, ".git")):
            return "skipped", "not a git checkout"
        code, cur_branch, _ = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if code or cur_branch != branch:
            return "skipped", f"on branch '{cur_branch}', not '{branch}'"
        code, dirty, _ = _git(root, "status", "--porcelain", "--untracked-files=no")
        if code or dirty:
            return "skipped", "there are local code changes (not touching them)"
        try:
            code, _, err = _git(root, "fetch", "--quiet", remote, branch, timeout=timeout)
        except subprocess.TimeoutExpired:
            return "offline", "GitHub didn't answer in time"
        if code:
            return "offline", (err.splitlines() or ["fetch failed"])[-1]
        _, old, _ = _git(root, "rev-parse", "HEAD")
        _, new, _ = _git(root, "rev-parse", f"{remote}/{branch}")
        if old == new:
            return "up_to_date", _short(root, old)
        if _git(root, "merge-base", "--is-ancestor", new, old)[0] == 0:
            return "up_to_date", "this copy is ahead of GitHub"
        if _git(root, "merge-base", "--is-ancestor", old, new)[0] != 0:
            return "skipped", "local commits that aren't on GitHub (won't merge automatically)"
        st = _load(root)
        if new in st.get("bad", []):
            return "skipped", f"{_short(root, new)} failed to start before - waiting for a newer push"
        code, _, err = _git(root, "merge", "--ff-only", "--quiet", new)
        if code:
            return "skipped", f"fast-forward failed: {err.splitlines()[-1] if err else code}"
        code, changed, _ = _git(root, "diff", "--name-only", old, new, "--", "requirements.txt")
        if changed:
            log("requirements changed - installing packages ...")
            pip(root)
        ok, why = smoke(root)
        if not ok:
            rollback(root, old, new, log=log, reason=" ".join(why))
            return "rolled_back", f"{_short(root, new)} wouldn't start ({' '.join(why)}) - staying on {_short(root, old)}"
        st.update(prev=old, new=new, pending=True)
        _save(root, st)
        return "updated", f"{_short(root, old)}  ->  {_short(root, new)}"
    except Exception as e:  # noqa - an update problem must never stop the game starting
        return "error", str(e)


def rollback(root, prev, bad, log=print, reason=""):
    """Go back to `prev` and remember `bad` so it isn't tried again."""
    code, _, err = _git(root, "reset", "--keep", "--quiet", prev)
    st = _load(root)
    st["bad"] = (st.get("bad", []) + [bad])[-20:]
    st.update(pending=False, rolled_back_to=prev)
    _save(root, st)
    if code:
        log(f"couldn't go back to {prev[:7]}: {err}")
        return False
    log(f"went back to {_short(root, prev)}" + (f"  ({reason})" if reason else ""))
    return True


def started_ok(root=ROOT):
    """Call once the program is properly running: the update is kept (or, after a rollback, the
    previous version works, so the crash really was the new version's fault)."""
    st = _load(root)
    if st.get("pending") or st.get("checking"):
        st["pending"] = False
        st.pop("checking", None)
        _save(root, st)


def crashed_after_update(root=ROOT, log=print):
    """The restarted program crashed before started_ok(): go back. True if it did."""
    st = _load(root)
    if not os.environ.get(ENV_UPDATED):
        return False
    if not st.get("pending") and st.get("checking"):
        # the previous version crashes too: not the update's fault (a camera, the config...), so
        # don't hold that commit back - it's tried again next start
        st["bad"] = [b for b in st.get("bad", []) if b != st.pop("checking")]
        _save(root, st)
        return False
    if not (st.get("pending") and st.get("prev")):
        return False
    log("The new version crashed while starting - going back to the one before.")
    ok = rollback(root, st["prev"], st.get("new", ""), log=log, reason="crashed on start")
    if ok:
        st = _load(root)
        st["checking"] = st.get("new", "")
        _save(root, st)
    return ok


def restart(old_sha=""):
    """Replace this process with a fresh `python -m dartvision <same arguments>`."""
    sys.stdout.flush()
    sys.stderr.flush()
    os.environ[ENV_UPDATED] = old_sha or "1"
    os.execv(sys.executable, [sys.executable, "-m", "dartvision", *sys.argv[1:]])
