import os
import subprocess
import time
from types import SimpleNamespace

import pytest

from mijen import runner, storage


# ── Basic execution ───────────────────────────────────────────────────────────

def test_successful_build_records_output(local_project, run_build):
    pid, _ = local_project
    build = run_build(pid, "echo hello; echo world")
    assert build.status == "success"
    assert "hello\nworld\n" in build.output_log
    assert build.end_time is not None


def test_failing_command_marks_build_failed(local_project, run_build):
    pid, _ = local_project
    build = run_build(pid, "echo before; exit 3")
    assert build.status == "failed"
    assert "before" in build.output_log
    assert "exit code 3" in build.output_log


def test_setup_command_runs_first_in_workspace(local_project, run_build):
    pid, path = local_project
    build = run_build(pid, "cat marker.txt", setup_command="echo from-setup > marker.txt")
    assert build.status == "success"
    assert "from-setup" in build.output_log
    assert (path / "marker.txt").exists()


def test_failing_setup_skips_main_command(local_project, run_build):
    pid, _ = local_project
    build = run_build(pid, "echo MAIN-RAN", setup_command="exit 1")
    assert build.status == "failed"
    assert "MAIN-RAN" not in build.output_log.replace("$ echo MAIN-RAN", "")


def test_missing_local_path_fails_cleanly(run_build, tmp_path):
    pid = storage.create_project("Gone", "local", str(tmp_path / "does-not-exist"))
    build = run_build(pid, "true")
    assert build.status == "failed"
    assert "Local path does not exist" in build.output_log


def test_run_task_unknown_id_returns_minus_one():
    assert runner.run_task("no-such-task") == -1


# ── Robustness ────────────────────────────────────────────────────────────────

def test_invalid_utf8_output_does_not_crash_build(local_project, run_build):
    pid, _ = local_project
    build = run_build(pid, r"printf '\377\376 bad bytes\n'; echo after")
    assert build.status == "success"
    assert "bad bytes" in build.output_log
    assert "after" in build.output_log


def test_nul_bytes_are_stripped_from_stored_log(local_project, run_build):
    pid, _ = local_project
    build = run_build(pid, r"printf 'a\000b\n'")
    assert build.status == "success"
    assert "\x00" not in build.output_log
    assert "ab" in build.output_log


def test_timeout_kills_silent_command(local_project, run_build, monkeypatch):
    monkeypatch.setattr(runner, "BUILD_TIMEOUT", 1)
    pid, _ = local_project

    t0 = time.monotonic()
    build = run_build(pid, "sleep 30")
    elapsed = time.monotonic() - t0

    assert build.status == "failed"
    assert "TIMED OUT" in build.output_log
    assert elapsed < 10


def test_timeout_covers_setup_and_main_together(local_project, run_build, monkeypatch):
    monkeypatch.setattr(runner, "BUILD_TIMEOUT", 2)
    pid, _ = local_project

    # Each step alone fits in the timeout, both together don't.
    build = run_build(pid, "sleep 1.5; echo MAIN-DONE", setup_command="sleep 1.5")
    assert build.status == "failed"
    assert "TIMED OUT" in build.output_log
    assert "MAIN-DONE" not in build.output_log.replace("echo MAIN-DONE", "")


def test_timeout_kills_child_processes(local_project, run_build, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "BUILD_TIMEOUT", 1)
    pid, _ = local_project
    pidfile = tmp_path / "child.pid"

    # The shell starts a background child, then waits on it.
    run_build(pid, f"sleep 60 & echo $! > {pidfile}; wait")

    child = int(pidfile.read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)   # child must be gone, not orphaned


def test_output_limit_stops_build(local_project, run_build, monkeypatch):
    monkeypatch.setattr(runner, "MAX_OUTPUT_BYTES", 2_000)
    pid, _ = local_project

    t0 = time.monotonic()
    build = run_build(pid, "yes 0123456789")
    assert time.monotonic() - t0 < 10
    assert build.status == "failed"
    assert "OUTPUT TRUNCATED" in build.output_log
    assert len(build.output_log) < 4_000


def test_secrets_are_not_visible_to_tasks(local_project, run_build, monkeypatch):
    monkeypatch.setenv("MIJEN_AUTH_PASS", "super-secret-pass")
    monkeypatch.setenv("WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setenv("SOME_OTHER_VAR", "visible")
    pid, _ = local_project

    build = run_build(pid, "env")
    assert build.status == "success"
    assert "super-secret-pass" not in build.output_log
    assert "hook-secret" not in build.output_log
    assert "DATABASE_URL" not in build.output_log
    assert "SOME_OTHER_VAR=visible" in build.output_log


def test_status_is_final_when_is_running_turns_false(local_project, monkeypatch):
    """The UI reads the DB as soon as is_running() is False; it must not see 'running'."""
    pid, _ = local_project
    tid = storage.create_task(pid, "t", "true")

    real_finish = storage.finish_build

    def slow_finish(*args):
        time.sleep(0.3)
        real_finish(*args)

    monkeypatch.setattr(storage, "finish_build", slow_finish)

    bid = runner.run_task(tid)
    while runner.is_running(bid):
        time.sleep(0.01)
    assert storage.get_build(bid).status == "success"
    runner.cleanup(bid)


# ── Live log buffer ───────────────────────────────────────────────────────────

def test_drain_lines_streams_output(local_project):
    pid, _ = local_project
    tid = storage.create_task(pid, "t", "echo one; echo two")
    bid = runner.run_task(tid)
    while runner.is_running(bid):
        time.sleep(0.05)
    lines = runner.drain_lines(bid)
    assert "one" in lines and "two" in lines
    assert runner.drain_lines(bid) == []      # drained
    runner.cleanup(bid)


def test_unwatched_finished_builds_are_reaped(local_project, monkeypatch):
    pid, _ = local_project
    tid = storage.create_task(pid, "t", "echo x")

    bid = runner.run_task(tid)
    while runner.is_running(bid):
        time.sleep(0.05)
    assert bid in runner._pending           # kept for a possible viewer

    monkeypatch.setattr(runner, "_REAP_AFTER_SECONDS", 0)
    other = runner.run_task(tid)             # next run reaps stale entries
    assert bid not in runner._pending
    assert bid not in runner._finished_at

    while runner.is_running(other):
        time.sleep(0.05)
    runner.cleanup(other)


# ── System packages ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("packages, bad", [
    ("cmake g++ ninja-build", []),
    ("libc6:amd64 python3=3.11.2-1 qt6-base-dev", []),
    ("-o APT::Update::Pre-Invoke::=touch", ["-o", "APT::Update::Pre-Invoke::=touch"]),
    ("good --allow-unauthenticated", ["--allow-unauthenticated"]),
    ("Bad_Name", ["Bad_Name"]),
    ("", []),
])
def test_invalid_packages(packages, bad):
    assert runner.invalid_packages(packages) == bad


def test_invalid_package_fails_build_before_apt(run_build, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(runner.subprocess, "run",
                        lambda *a, **k: calls.append(a) or subprocess.CompletedProcess(a, 0))
    pid = storage.create_project("P", "local", str(tmp_path), system_packages="-o evil")

    build = run_build(pid, "true")
    assert build.status == "failed"
    assert "Invalid system package" in build.output_log
    assert calls == []          # apt-get never invoked


# ── GitHub source ─────────────────────────────────────────────────────────────

@pytest.fixture
def git_remote(tmp_path):
    """A local git repo usable as a clone source. Returns .path and .git(*args)."""
    repo = tmp_path / "remote"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)

    git("init", "-q", "-b", "main")
    (repo / "hello.txt").write_text("v1\n")
    git("add", ".")
    git("commit", "-q", "-m", "v1")
    return SimpleNamespace(path=repo, git=git)


def test_github_project_clones_then_pulls(run_build, git_remote):
    pid = storage.create_project("Repo", "github", f"file://{git_remote.path}")

    first = run_build(pid, "cat hello.txt")
    assert first.status == "success", first.output_log
    assert "[git clone" in first.output_log
    assert "v1" in first.output_log

    (git_remote.path / "hello.txt").write_text("v2\n")
    git_remote.git("commit", "-q", "-am", "v2")

    second = run_build(pid, "cat hello.txt")
    assert second.status == "success", second.output_log
    assert "[git pull --ff-only]" in second.output_log
    assert "v2" in second.output_log


def test_git_failure_shows_git_error(run_build, tmp_path):
    pid = storage.create_project("Bad", "github", f"file://{tmp_path / 'nope'}")
    build = run_build(pid, "true")
    assert build.status == "failed"
    # git's own explanation must reach the log, not just an exit code
    assert "does not exist" in build.output_log or "not a git repository" in build.output_log \
        or "fatal:" in build.output_log


def test_repo_url_cannot_inject_git_options(run_build, tmp_path):
    marker = tmp_path / "pwned"
    pid = storage.create_project("Evil", "github", f"--upload-pack=touch {marker}")
    build = run_build(pid, "true")
    assert build.status == "failed"
    assert not marker.exists()


def test_concurrent_builds_share_one_clone(git_remote):
    pid = storage.create_project("Repo", "github", f"file://{git_remote.path}")
    tid = storage.create_task(pid, "t", "cat hello.txt")

    bids = [runner.run_task(tid) for _ in range(4)]
    for bid in bids:
        while runner.is_running(bid):
            time.sleep(0.05)
        runner.cleanup(bid)

    statuses = [storage.get_build(b).status for b in bids]
    assert statuses == ["success"] * 4, [storage.get_build(b).output_log for b in bids]


def test_remove_workspace(run_build, git_remote):
    pid = storage.create_project("Repo", "github", f"file://{git_remote.path}")
    assert run_build(pid, "true").status == "success"
    assert (runner.WORKSPACES_DIR / pid).is_dir()

    runner.remove_workspace(pid)
    assert not (runner.WORKSPACES_DIR / pid).exists()
    runner.remove_workspace(pid)   # idempotent
