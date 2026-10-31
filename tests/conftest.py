"""
Test configuration.

mijen.storage creates its engine and mijen.runner reads its limits at import
time, so the environment must be set up before any mijen module is imported.
"""
import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="mijen-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["WORKSPACES_DIR"] = str(_TMP / "workspaces")

from mijen import runner, storage  # noqa: E402
from mijen.models import Base      # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts with an empty schema."""
    Base.metadata.drop_all(storage.engine)
    storage.init_db()
    yield


@pytest.fixture
def local_project(tmp_path):
    """A 'local' project whose workspace is an empty temp dir. Returns (pid, path)."""
    pid = storage.create_project("Local", "local", str(tmp_path))
    return pid, tmp_path


@pytest.fixture
def run_build():
    """
    Run a task to completion and return its BuildDTO.

    Usage: build = run_build(pid, "echo hi", setup_command="")
    """
    import time

    def _run(pid: str, command: str, setup_command: str = "", wait: float = 20.0):
        tid = storage.create_task(pid, "task", command, setup_command=setup_command)
        bid = runner.run_task(tid)
        assert bid > 0
        deadline = time.monotonic() + wait
        while runner.is_running(bid):
            assert time.monotonic() < deadline, "build did not finish in time"
            time.sleep(0.05)
        build = storage.get_build(bid)
        runner.cleanup(bid)
        return build

    return _run
