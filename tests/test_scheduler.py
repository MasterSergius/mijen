import pytest

from mijen import scheduler, storage


@pytest.mark.parametrize("expr", [
    "0 * * * *",
    "30 6 * * 1-5",
    "*/15 * * * *",
    "  0 2 * * *  ",
])
def test_validate_cron_accepts_valid(expr):
    assert scheduler.validate_cron(expr) is None


@pytest.mark.parametrize("expr", [
    "",
    "* * * *",
    "* * * * * *",
    "99 * * * *",
    "0 25 * * *",
    "0 0 * * funday",
])
def test_validate_cron_rejects_invalid(expr):
    assert scheduler.validate_cron(expr)


@pytest.fixture
def running_scheduler():
    scheduler._scheduler.start(paused=True)   # paused: jobs are registered, never fired
    yield scheduler._scheduler
    scheduler._scheduler.remove_all_jobs()
    scheduler._scheduler.shutdown(wait=False)
    # BackgroundScheduler can't be restarted after shutdown; give later tests a new one
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler._scheduler = BackgroundScheduler(timezone="UTC")


def test_sync_registers_cron_jobs_and_drops_deleted(running_scheduler):
    pid = storage.create_project("P", "local", "/x")
    tid = storage.create_task(pid, "T", "true")
    trig = storage.add_trigger(tid, "cron", {"cron": "0 * * * *"})
    storage.add_trigger(tid, "cron", {"cron": "not a cron"})   # ignored, not fatal

    scheduler.sync()
    assert [j.id for j in running_scheduler.get_jobs()] == [str(trig)]

    storage.delete_task(tid)
    scheduler.sync()
    assert running_scheduler.get_jobs() == []
