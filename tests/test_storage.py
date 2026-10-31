from mijen import storage


def test_init_db_works_on_sqlite():
    # fresh_db already ran init_db(); running it again must be harmless
    storage.init_db()
    assert storage.get_all_projects() == []


def test_project_crud():
    pid = storage.create_project("Alpha", "github", "https://github.com/u/r",
                                 system_packages="  cmake  ")
    p = storage.get_project(pid)
    assert p.name == "Alpha"
    assert p.system_packages == "cmake"

    storage.update_project_packages(pid, "   ")
    assert storage.get_project(pid).system_packages is None

    storage.delete_project(pid)
    assert storage.get_project(pid) is None


def test_projects_sorted_by_name():
    storage.create_project("b", "local", "/x")
    storage.create_project("a", "local", "/y")
    assert [p.name for p in storage.get_all_projects()] == ["a", "b"]


def test_task_crud_and_cascade_delete():
    pid = storage.create_project("P", "local", "/x")
    tid = storage.create_task(pid, "Build", "make", setup_command=" ")
    assert storage.get_task(tid).setup_command is None

    storage.update_task(tid, " Test ", " make test ", "pip install x")
    t = storage.get_task(tid)
    assert (t.name, t.command, t.setup_command) == ("Test", "make test", "pip install x")

    trig = storage.add_trigger(tid, "cron", {"cron": "0 * * * *"})
    bid = storage.create_build(tid)
    assert storage.get_all_triggers()[0].id == trig

    storage.delete_project(pid)
    assert storage.get_task(tid) is None
    assert storage.get_all_triggers() == []
    assert storage.get_build(bid) is None


def test_build_lifecycle_and_nul_stripping():
    pid = storage.create_project("P", "local", "/x")
    tid = storage.create_task(pid, "T", "true")
    bid = storage.create_build(tid)

    b = storage.get_build(bid)
    assert b.status == "running"
    assert b.end_time is None

    storage.finish_build(bid, "success", "ok\x00\n")
    b = storage.get_build(bid)
    assert b.status == "success"
    assert b.output_log == "ok\n"
    assert b.end_time >= b.start_time


def test_history_newest_first():
    pid = storage.create_project("P", "local", "/x")
    tid = storage.create_task(pid, "T", "true")
    first = storage.create_build(tid)
    second = storage.create_build(tid)
    assert [b.id for b in storage.get_task(tid).history] == [second, first]


def test_fail_interrupted_builds():
    pid = storage.create_project("P", "local", "/x")
    tid = storage.create_task(pid, "T", "true")
    stuck = storage.create_build(tid)
    done = storage.create_build(tid)
    storage.finish_build(done, "success", "fine")

    assert storage.fail_interrupted_builds() == 1

    b = storage.get_build(stuck)
    assert b.status == "failed"
    assert b.end_time is not None
    assert "INTERRUPTED" in b.output_log
    assert storage.get_build(done).status == "success"
    assert storage.fail_interrupted_builds() == 0
