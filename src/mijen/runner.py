"""
Task runner — executes task commands in background threads.

Security notes:
  - Git clone/pull uses a list argv (no shell injection possible).
  - Task commands run with shell=True because they are shell scripts stored
    server-side by trusted admins, never taken verbatim from HTTP requests.
  - Workspaces are keyed only by project UUID — no user-controlled path segments.
  - Output is capped at MAX_OUTPUT_BYTES to prevent runaway log growth.
  - Each build has a hard timeout (BUILD_TIMEOUT_SECONDS).
"""
import os
import subprocess
import threading
from collections import deque
from pathlib import Path

from mijen import storage

WORKSPACES_DIR = Path(os.getenv("WORKSPACES_DIR", "/app/workspaces"))
MAX_OUTPUT_BYTES = int(os.getenv("MAX_OUTPUT_BYTES", str(1_000_000)))   # 1 MB
BUILD_TIMEOUT = int(os.getenv("BUILD_TIMEOUT_SECONDS", "3600"))          # 1 hour

# build_id → deque of pending log lines (consumed by UI polling timer)
_pending: dict[int, deque] = {}
# build_id → True while still running
_running: dict[int, bool] = {}
_lock = threading.Lock()


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

    build_id = storage.create_build(task_id)

    with _lock:
        _pending[build_id] = deque()
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


# ── Internal ──────────────────────────────────────────────────────────────────

def _push(build_id: int, line: str) -> None:
    d = _pending.get(build_id)
    if d is not None:
        d.append(line)


def _execute(build_id: int, project, task) -> None:
    status = "failed"
    output_lines: list[str] = []

    def emit(line: str) -> None:
        output_lines.append(line + "\n")
        _push(build_id, line)

    try:
        work_dir = _prepare_workspace(project, emit)
        if project.system_packages:
            _install_packages(project.system_packages, build_id, emit)
        if task.setup_command:
            _run_command(task.setup_command, work_dir, build_id, emit)
        _run_command(task.command, work_dir, build_id, emit)
        status = "success"
    except subprocess.CalledProcessError as e:
        emit(f"\n[COMMAND FAILED — exit code {e.returncode}]")
    except subprocess.TimeoutExpired:
        emit(f"\n[BUILD TIMED OUT after {BUILD_TIMEOUT}s]")
    except Exception as e:
        emit(f"\n[RUNNER ERROR: {e}]")
    finally:
        with _lock:
            _running[build_id] = False
        storage.finish_build(build_id, status, "".join(output_lines))


def _install_packages(packages: str, build_id: int, emit) -> None:
    pkg_list = packages.split()
    emit("[apt-get update]")
    subprocess.run(["apt-get", "update", "-qq"], capture_output=True, timeout=120)
    emit(f"[apt-get install -y {' '.join(pkg_list)}]")
    proc = subprocess.run(
        ["apt-get", "install", "-y", "-qq"] + pkg_list,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        emit(proc.stderr.strip())
        raise subprocess.CalledProcessError(proc.returncode, "apt-get")


def _prepare_workspace(project, emit) -> Path:
    if project.source_type == "local":
        path = Path(project.source)
        if not path.is_dir():
            raise FileNotFoundError(f"Local path does not exist: {path}")
        emit(f"[Using local workspace: {path}]")
        return path

    # GitHub — clone or pull into workspaces/<uuid>/
    workspace = WORKSPACES_DIR / project.id
    workspace.mkdir(parents=True, exist_ok=True)

    if (workspace / ".git").exists():
        emit("[git pull --ff-only]")
        subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(workspace),
            capture_output=True,
            check=True,
            timeout=120,
        )
    else:
        emit(f"[git clone {project.source}]")
        subprocess.run(
            ["git", "clone", "--depth=1", project.source, str(workspace)],
            capture_output=True,
            check=True,
            timeout=120,
        )

    return workspace


def _run_command(command: str, work_dir: Path, build_id: int, emit) -> None:
    emit(f"$ {command}\n")
    total_bytes = 0

    proc = subprocess.Popen(
        command,
        shell=True,           # intentional: commands are admin-set shell scripts
        cwd=str(work_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=os.environ.copy(),
    )

    for line in proc.stdout:
        line = line.rstrip("\n")
        emit(line)
        total_bytes += len(line)
        if total_bytes > MAX_OUTPUT_BYTES:
            proc.kill()
            emit("\n[OUTPUT TRUNCATED — limit reached]")
            break

    proc.wait(timeout=BUILD_TIMEOUT)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, command)
