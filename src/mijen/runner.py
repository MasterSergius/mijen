"""
Task runner — executes task commands in background threads.

Security notes:
  - Git clone/pull and apt-get use a list argv (no shell injection possible);
    the repo URL is passed after "--" and package names are validated so
    neither can be interpreted as an option.
  - Task commands run with shell=True because they are shell scripts stored
    server-side by trusted admins, never taken verbatim from HTTP requests.
  - Task commands do NOT inherit MiJen's own secrets (DB URL, auth password,
    webhook secret): build scripts from cloned repos must not be able to read them.
  - Workspaces are keyed only by project UUID — no user-controlled path segments.
  - Output is capped at MAX_OUTPUT_BYTES per build to prevent runaway log growth.
  - Each build has a hard timeout (BUILD_TIMEOUT_SECONDS) covering all steps.
    On timeout or truncation the whole process group is killed, not just the shell.
"""
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from mijen import storage

WORKSPACES_DIR = Path(os.getenv("WORKSPACES_DIR", "/app/workspaces"))
MAX_OUTPUT_BYTES = int(os.getenv("MAX_OUTPUT_BYTES", str(1_000_000)))   # 1 MB
BUILD_TIMEOUT = int(os.getenv("BUILD_TIMEOUT_SECONDS", "3600"))          # 1 hour

# Environment variables that must never reach task commands.
_SECRET_ENV_VARS = {
    "DATABASE_URL",
    "WEBHOOK_SECRET",
    "MIJEN_AUTH_USER",
    "MIJEN_AUTH_PASS",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
}

# Debian package names (optionally with =version / :arch); must not start with "-".
_APT_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]*(:[a-z0-9\-]+)?(=[A-Za-z0-9.+~:\-]+)?$")

# Log lines buffered per build for live streaming. Bounded so an unwatched
# build (cron / webhook) can't grow memory without limit.
_MAX_PENDING_LINES = 10_000
# Finished builds nobody is watching are forgotten after this many seconds.
_REAP_AFTER_SECONDS = 300

# build_id → deque of pending log lines (consumed by UI polling timer)
_pending: dict[int, deque] = {}
# build_id → True while still running
_running: dict[int, bool] = {}
# build_id → monotonic time the build finished (for reaping)
_finished_at: dict[int, float] = {}
_lock = threading.Lock()

# project_id → lock serialising git clone/pull into the shared workspace
_workspace_locks: dict[str, threading.Lock] = {}


class BuildTimeout(Exception):
    pass


class OutputLimitExceeded(Exception):
    pass


# ── Public API ────────────────────────────────────────────────────────────────

def run_task(task_id: str) -> int:
    """
    Kick off a build in a background thread.
    Returns the build_id immediately so the caller can track progress.
    Returns -1 if the task or project was not found.
    """
    task = storage.get_task(task_id)
    if task is None:
        return -1

    project = storage.get_project(task.project_id)
    if project is None:
        return -1

    _reap_finished()
    build_id = storage.create_build(task_id)

    with _lock:
        _pending[build_id] = deque(maxlen=_MAX_PENDING_LINES)
        _running[build_id] = True

    thread = threading.Thread(
        target=_execute,
        args=(build_id, project, task),
        daemon=True,
    )
    thread.start()
    return build_id


def is_running(build_id: int) -> bool:
    return _running.get(build_id, False)


def drain_lines(build_id: int) -> list[str]:
    """
    Pop and return all pending log lines since the last call.
    Thread-safe via deque.popleft().
    """
    d = _pending.get(build_id)
    if d is None:
        return []
    lines = []
    try:
        while True:
            lines.append(d.popleft())
    except IndexError:
        pass
    return lines


def cleanup(build_id: int) -> None:
    with _lock:
        _pending.pop(build_id, None)
        _running.pop(build_id, None)
        _finished_at.pop(build_id, None)


def invalid_packages(packages: str) -> list[str]:
    """Return the space-separated package names that are not valid apt names."""
    return [p for p in packages.split() if not _APT_PACKAGE_RE.match(p)]


def remove_workspace(project_id: str) -> None:
    """Delete the cloned workspace of a GitHub project (no-op if absent)."""
    workspace = WORKSPACES_DIR / project_id
    if workspace.is_dir():
        shutil.rmtree(workspace, ignore_errors=True)


# ── Internal ──────────────────────────────────────────────────────────────────

def _reap_finished() -> None:
    """Forget finished builds that no UI picked up (e.g. cron / webhook runs)."""
    cutoff = time.monotonic() - _REAP_AFTER_SECONDS
    with _lock:
        stale = [bid for bid, t in _finished_at.items() if t < cutoff]
        for bid in stale:
            _pending.pop(bid, None)
            _running.pop(bid, None)
            _finished_at.pop(bid, None)


def _push(build_id: int, line: str) -> None:
    d = _pending.get(build_id)
    if d is not None:
        d.append(line)


def _task_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _SECRET_ENV_VARS}


def _execute(build_id: int, project, task) -> None:
    status = "failed"
    output_lines: list[str] = []
    deadline = time.monotonic() + BUILD_TIMEOUT
    budget = {"bytes": MAX_OUTPUT_BYTES}

    def emit(line: str) -> None:
        output_lines.append(line + "\n")
        _push(build_id, line)

    try:
        work_dir = _prepare_workspace(project, emit)
        if project.system_packages:
            _install_packages(project.system_packages, emit)
        if task.setup_command:
            _run_command(task.setup_command, work_dir, emit, deadline, budget)
        _run_command(task.command, work_dir, emit, deadline, budget)
        status = "success"
    except subprocess.CalledProcessError as e:
        emit(f"\n[COMMAND FAILED — exit code {e.returncode}]")
    except (BuildTimeout, subprocess.TimeoutExpired):
        emit(f"\n[BUILD TIMED OUT after {BUILD_TIMEOUT}s]")
    except OutputLimitExceeded:
        emit(f"\n[OUTPUT TRUNCATED — limit of {MAX_OUTPUT_BYTES} bytes reached, build stopped]")
    except Exception as e:
        emit(f"\n[RUNNER ERROR: {e}]")
    finally:
        # Persist the result BEFORE flagging the build as finished: the UI
        # reads the final status from the DB as soon as is_running() is False.
        try:
            storage.finish_build(build_id, status, "".join(output_lines))
        finally:
            with _lock:
                _running[build_id] = False
                _finished_at[build_id] = time.monotonic()


def _install_packages(packages: str, emit) -> None:
    pkg_list = packages.split()
    bad = invalid_packages(packages)
    if bad:
        raise ValueError(f"Invalid system package name(s): {' '.join(bad)}")

    emit("[apt-get update]")
    subprocess.run(["apt-get", "update", "-qq"], capture_output=True, timeout=120)
    emit(f"[apt-get install -y {' '.join(pkg_list)}]")
    proc = subprocess.run(
        ["apt-get", "install", "-y", "-qq", "--"] + pkg_list,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=300,
    )
    if proc.returncode != 0:
        emit(proc.stderr.strip())
        raise subprocess.CalledProcessError(proc.returncode, "apt-get")


def _git(args: list[str], emit, cwd: Path | None = None) -> None:
    """Run a git command; on failure, show git's own error output in the log."""
    proc = subprocess.run(
        ["git"] + args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=120,
        env={**_task_env(), "GIT_TERMINAL_PROMPT": "0"},   # never hang on a password prompt
    )
    if proc.returncode != 0:
        output = (proc.stderr or proc.stdout).strip()
        if output:
            emit(output)
        raise subprocess.CalledProcessError(proc.returncode, ["git"] + args)


def _prepare_workspace(project, emit) -> Path:
    if project.source_type == "local":
        path = Path(project.source)
        if not path.is_dir():
            raise FileNotFoundError(f"Local path does not exist: {path}")
        emit(f"[Using local workspace: {path}]")
        return path

    # GitHub — clone or pull into workspaces/<uuid>/.
    # Serialised per project: two concurrent builds must not clone into or
    # pull the same directory at the same time.
    with _lock:
        ws_lock = _workspace_locks.setdefault(project.id, threading.Lock())

    with ws_lock:
        workspace = WORKSPACES_DIR / project.id
        workspace.mkdir(parents=True, exist_ok=True)

        if (workspace / ".git").exists():
            emit("[git pull --ff-only]")
            _git(["pull", "--ff-only"], emit, cwd=workspace)
        else:
            emit(f"[git clone {project.source}]")
            _git(["clone", "--depth=1", "--", project.source, str(workspace)], emit)

    return workspace


def _run_command(command: str, work_dir: Path, emit, deadline: float, budget: dict) -> None:
    """
    Run a shell command, streaming its output.

    Raises BuildTimeout if the build deadline passes, OutputLimitExceeded if the
    build's output budget is exhausted, CalledProcessError on non-zero exit.
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise BuildTimeout()

    emit(f"$ {command}\n")

    proc = subprocess.Popen(
        command,
        shell=True,           # intentional: commands are admin-set shell scripts
        cwd=str(work_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",     # never fail a build on non-UTF-8 output
        env=_task_env(),
        start_new_session=True,   # own process group, so we can kill all children
    )

    timed_out = threading.Event()

    def _on_timeout():
        timed_out.set()
        _kill_group(proc)

    # The watchdog fires even if the command prints nothing (reading stdout
    # blocks until EOF, so a check inside the read loop would never run).
    watchdog = threading.Timer(remaining, _on_timeout)
    watchdog.daemon = True
    watchdog.start()

    truncated = False
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            budget["bytes"] -= len(line.encode("utf-8", errors="replace")) + 1
            if budget["bytes"] < 0:
                truncated = True
                _kill_group(proc)
                break
            emit(line)
        proc.wait()
    finally:
        watchdog.cancel()
        proc.stdout.close()

    if timed_out.is_set():
        raise BuildTimeout()
    if truncated:
        raise OutputLimitExceeded()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, command)


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
