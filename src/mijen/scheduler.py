"""
Cron scheduler — wraps APScheduler.
Call init() once at app startup; call sync() after any trigger change.
"""
import logging
from mijen import storage

log = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _scheduler = BackgroundScheduler(timezone="UTC")
    _available = True
except ImportError:
    _scheduler = None
    _available = False
    log.warning("APScheduler not installed — cron triggers disabled. Run: uv add apscheduler")


def init() -> None:
    if not _available:
        return
    _scheduler.start()
    sync()
    log.info("Scheduler started")


def shutdown() -> None:
    if _available and _scheduler.running:
        _scheduler.shutdown(wait=False)


def sync() -> None:
    """Reload all cron jobs from DB. Call after any trigger create/delete."""
    if not _available:
        return
    _scheduler.remove_all_jobs()
    for trigger in storage.get_all_triggers():
        if trigger.trigger_type != "cron":
            continue
        expr = trigger.config.get("cron", "").strip()
        if not expr:
            continue
        try:
            _scheduler.add_job(
                _fire,
                CronTrigger.from_crontab(expr, timezone="UTC"),
                args=[trigger.task_id],
                id=str(trigger.id),
                replace_existing=True,
            )
            log.info("Cron registered: task=%s expr=%s", trigger.task_id, expr)
        except Exception as e:
            log.warning("Bad cron expression for trigger %s: %s", trigger.id, e)


def _fire(task_id: str) -> None:
    from mijen.runner import run_task
    log.info("Cron firing task %s", task_id)
    run_task(task_id)
