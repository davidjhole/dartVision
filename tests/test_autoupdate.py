"""Update on start, against real throwaway git repos:  python -m pytest tests/test_autoupdate.py"""
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dartvision import autoupdate as au  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="needs git")


def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


def commit(cwd, name, text, msg):
    (cwd / name).write_text(text)
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", msg)
    return git(cwd, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path):
    """origin (bare), 'github' (where pushes come from) and 'pi' (the installed copy)."""
    origin, gh, pi = tmp_path / "origin.git", tmp_path / "github", tmp_path / "pi"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(gh)], check=True, capture_output=True)
    git(gh, "checkout", "-q", "-b", "main")
    commit(gh, "app.py", "v1\n", "first")
    commit(gh, ".gitignore", f"{au.STATE_FILE}\nconfig.yaml\n", "ignore")
    git(gh, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", str(origin), str(pi)], check=True, capture_output=True)
    return gh, pi


def push(gh, text="v2\n", name="app.py", msg="second"):
    sha = commit(gh, name, text, msg)
    git(gh, "push", "-q", "origin", "main")
    return sha


def run(pi, **kw):
    kw.setdefault("smoke", lambda root: (True, []))
    kw.setdefault("pip", lambda root: None)
    kw.setdefault("log", lambda *a: None)
    return au.update(str(pi), **kw)


def head(pi):
    return git(pi, "rev-parse", "HEAD")


def state(pi):
    p = pi / au.STATE_FILE
    return json.loads(p.read_text()) if p.exists() else {}


def test_up_to_date(repos):
    _, pi = repos
    assert run(pi)[0] == "up_to_date"


def test_fast_forwards_to_a_new_push(repos):
    gh, pi = repos
    old = head(pi)
    new = push(gh)
    res, msg = run(pi)
    assert res == "updated" and "second" in msg
    assert head(pi) == new and (pi / "app.py").read_text() == "v2\n"
    st = state(pi)
    assert st["prev"] == old and st["new"] == new and st["pending"] is True


def test_your_files_are_left_alone(repos):
    gh, pi = repos
    (pi / "config.yaml").write_text("mine\n")        # untracked, like config / calib / recordings
    push(gh)
    assert run(pi)[0] == "updated"
    assert (pi / "config.yaml").read_text() == "mine\n"


def test_local_code_changes_are_not_touched(repos):
    gh, pi = repos
    (pi / "app.py").write_text("my tweak\n")
    old = head(pi)
    push(gh)
    res, msg = run(pi)
    assert res == "skipped" and "local code changes" in msg
    assert head(pi) == old and (pi / "app.py").read_text() == "my tweak\n"


def test_other_branch_is_left_alone(repos):
    gh, pi = repos
    git(pi, "checkout", "-q", "-b", "experiment")
    push(gh)
    res, msg = run(pi)
    assert res == "skipped" and "experiment" in msg


def test_local_commits_dont_get_merged(repos):
    gh, pi = repos
    commit(pi, "local.txt", "x", "local work")
    old = head(pi)
    push(gh)
    res, msg = run(pi)
    assert res == "skipped" and "local commits" in msg and head(pi) == old


def test_ahead_of_github_is_fine(repos):
    _, pi = repos
    commit(pi, "local.txt", "x", "local work")
    assert run(pi) == ("up_to_date", "this copy is ahead of GitHub")


def test_offline_starts_what_is_here(repos):
    _, pi = repos
    git(pi, "remote", "set-url", "origin", str(pi.parent / "gone.git"))
    old = head(pi)
    assert run(pi)[0] == "offline" and head(pi) == old


def test_not_a_git_checkout(tmp_path):
    assert au.update(str(tmp_path))[0] == "skipped"


def test_requirements_change_installs_packages(repos):
    gh, pi = repos
    calls = []
    push(gh)
    run(pi, pip=calls.append)
    assert calls == []
    push(gh, "numpy\n", "requirements.txt", "deps")
    run(pi, pip=calls.append)
    assert calls == [str(pi)]


def test_new_code_that_wont_start_is_rolled_back(repos):
    gh, pi = repos
    old = head(pi)
    bad = push(gh, "broken\n")
    res, msg = run(pi, smoke=lambda root: (False, ["SyntaxError"]))
    assert res == "rolled_back" and "SyntaxError" in msg
    assert head(pi) == old and (pi / "app.py").read_text() == "v1\n"
    assert bad in state(pi)["bad"]
    # next start: don't try the same broken commit again
    assert run(pi)[0] == "skipped" and head(pi) == old
    # a fix pushed later is taken
    fixed = push(gh, "v3\n", msg="fix")
    assert run(pi)[0] == "updated" and head(pi) == fixed


def test_crash_after_restart_goes_back(repos, monkeypatch):
    gh, pi = repos
    old = head(pi)
    new = push(gh)
    assert run(pi)[0] == "updated"
    monkeypatch.setenv(au.ENV_UPDATED, old)
    assert au.crashed_after_update(str(pi), log=lambda *a: None) is True
    assert head(pi) == old and new in state(pi)["bad"]
    assert au.crashed_after_update(str(pi), log=lambda *a: None) is False    # only once


def test_crash_that_also_happens_on_the_old_version_isnt_blamed_on_the_update(repos, monkeypatch):
    gh, pi = repos
    old = head(pi)
    new = push(gh)
    run(pi)
    monkeypatch.setenv(au.ENV_UPDATED, old)
    assert au.crashed_after_update(str(pi), log=lambda *a: None) is True      # new one crashed: back
    assert new in state(pi)["bad"]
    assert au.crashed_after_update(str(pi), log=lambda *a: None) is False     # old one crashes too
    assert new not in state(pi)["bad"]
    monkeypatch.delenv(au.ENV_UPDATED)
    assert run(pi)[0] == "updated" and head(pi) == new                     # tried again next start


def test_crash_blamed_on_the_update_when_the_old_version_runs(repos, monkeypatch):
    gh, pi = repos
    old = head(pi)
    new = push(gh)
    run(pi)
    monkeypatch.setenv(au.ENV_UPDATED, old)
    au.crashed_after_update(str(pi), log=lambda *a: None)
    au.started_ok(str(pi))                                                 # old version runs fine
    assert new in state(pi)["bad"] and "checking" not in state(pi)
    monkeypatch.delenv(au.ENV_UPDATED)
    assert run(pi)[0] == "skipped"


def test_started_ok_keeps_the_update(repos, monkeypatch):
    gh, pi = repos
    push(gh)
    run(pi)
    au.started_ok(str(pi))
    monkeypatch.setenv(au.ENV_UPDATED, "x")
    assert au.crashed_after_update(str(pi), log=lambda *a: None) is False
    assert state(pi)["pending"] is False


def test_crash_without_an_update_does_nothing(repos, monkeypatch):
    _, pi = repos
    monkeypatch.delenv(au.ENV_UPDATED, raising=False)
    assert au.crashed_after_update(str(pi), log=lambda *a: None) is False


def test_smoke_test_on_this_checkout():
    ok, why = au._smoke_test(au.ROOT)
    assert ok, why


def test_smoke_test_catches_broken_code(tmp_path):
    shutil.copytree(os.path.join(au.ROOT, "dartvision"), tmp_path / "dartvision")
    (tmp_path / "dartvision" / "games.py").write_text("def broken(:\n")
    ok, why = au._smoke_test(str(tmp_path))
    assert not ok and "SyntaxError" in " ".join(why)
