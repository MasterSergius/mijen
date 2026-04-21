"""
Storage layer — all DB access goes through here.
Returns plain dataclasses, never raw ORM objects, so callers have no
SQLAlchemy session dependency and DetachedInstanceError is impossible.
"""
import os
import uuid
import datetime
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, selectinload

from mijen.models import Base, Project, Task, Trigger, BuildHistory

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./mijen.db")
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


# ── DTOs ──────────────────────────────────────────────────────────────────────

@dataclass
class TriggerDTO:
    id: int
    task_id: str
    trigger_type: str
    config: dict


@dataclass
class BuildDTO:
    id: int
    task_id: str
    start_time: datetime.datetime
    end_time: Optional[datetime.datetime]
    status: str
    output_log: Optional[str]


@dataclass
class TaskDTO:
    id: str
    project_id: str
    name: str
    command: str
    setup_command: Optional[str] = None
    triggers: list[TriggerDTO] = field(default_factory=list)
    history: list[BuildDTO] = field(default_factory=list)


@dataclass
class ProjectDTO:
    id: str
    name: str
    source_type: str
    source: str
    system_packages: Optional[str] = None
    tasks: list[TaskDTO] = field(default_factory=list)


# ── Converters ────────────────────────────────────────────────────────────────

def _trigger_dto(t: Trigger) -> TriggerDTO:
    return TriggerDTO(
        id=t.id,
        task_id=t.task_id,
        trigger_type=t.trigger_type,
        config=t.config or {},
    )


def _build_dto(b: BuildHistory) -> BuildDTO:
    return BuildDTO(
        id=b.id,
        task_id=b.task_id,
        start_time=b.start_time,
        end_time=b.end_time,
        status=b.status,
        output_log=b.output_log,
    )


def _task_dto(t: Task, include_history: bool = False) -> TaskDTO:
    return TaskDTO(
        id=t.id,
        project_id=t.project_id,
        name=t.name,
        command=t.command,
        setup_command=t.setup_command or None,
        triggers=[_trigger_dto(tr) for tr in t.triggers],
        history=[_build_dto(b) for b in t.history] if include_history else [],
    )


def _project_dto(p: Project, include_tasks: bool = True) -> ProjectDTO:
    return ProjectDTO(
        id=p.id,
        name=p.name,
        source_type=p.source_type,
        source=p.source,
        system_packages=p.system_packages or None,
        tasks=[_task_dto(t) for t in p.tasks] if include_tasks else [],
    )


# ── Init ──────────────────────────────────────────────────────────────────────

def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """
    Incremental schema migrations that create_all() won't handle
    (it only creates missing tables, never alters existing ones).
    Each step uses IF NOT EXISTS / IF EXISTS so no exceptions are raised
    and the transaction never enters an aborted state.
    """
    with engine.begin() as conn:
        # v0 → v1: projects.url renamed to projects.source + new source_type column
        conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS "
            "source_type VARCHAR NOT NULL DEFAULT 'github'"
        ))
        conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS source VARCHAR"
        ))
        # backfill source from the old url column and drop it.
        # wrapped in a DO block so the UPDATE is only parsed when url exists.
        conn.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'projects' AND column_name = 'url'
                ) THEN
                    UPDATE projects SET source = url WHERE source IS NULL;
                    ALTER TABLE projects DROP COLUMN url;
                END IF;
            END $$;
        """))
        # v2: system_packages on projects, setup_command on tasks
        conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS system_packages TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS setup_command TEXT"
        ))


# ── Projects ──────────────────────────────────────────────────────────────────

def get_all_projects() -> list[ProjectDTO]:
    with SessionLocal() as session:
        rows = (
            session.query(Project)
            .options(selectinload(Project.tasks))
            .order_by(Project.name)
            .all()
        )
        return [_project_dto(p) for p in rows]


def get_project(pid: str) -> Optional[ProjectDTO]:
    with SessionLocal() as session:
        row = (
            session.query(Project)
            .options(
                selectinload(Project.tasks).selectinload(Task.triggers),
                selectinload(Project.tasks).selectinload(Task.history),
            )
            .filter(Project.id == pid)
            .first()
        )
        if row is None:
            return None
        return _project_dto(row)


def create_project(name: str, source_type: str, source: str,
                   system_packages: str = "") -> str:
    pid = str(uuid.uuid4())
    with SessionLocal() as session:
        session.add(Project(
            id=pid, name=name, source_type=source_type, source=source,
            system_packages=system_packages.strip() or None,
        ))
        session.commit()
    return pid


def update_project_packages(pid: str, system_packages: str) -> None:
    with SessionLocal() as session:
        row = session.query(Project).filter(Project.id == pid).first()
        if row:
            row.system_packages = system_packages.strip() or None
            session.commit()


def delete_project(pid: str) -> None:
    with SessionLocal() as session:
        row = session.query(Project).filter(Project.id == pid).first()
        if row:
            session.delete(row)
            session.commit()


# ── Tasks ─────────────────────────────────────────────────────────────────────

def get_task(tid: str) -> Optional[TaskDTO]:
    with SessionLocal() as session:
        row = (
            session.query(Task)
            .options(
                selectinload(Task.triggers),
                selectinload(Task.history),
            )
            .filter(Task.id == tid)
            .first()
        )
        if row is None:
            return None
        return _task_dto(row, include_history=True)


def create_task(pid: str, name: str, command: str, setup_command: str = "") -> str:
    tid = str(uuid.uuid4())
    with SessionLocal() as session:
        session.add(Task(
            id=tid, project_id=pid, name=name, command=command,
            setup_command=setup_command.strip() or None,
        ))
        session.commit()
    return tid


def update_task(tid: str, name: str, command: str, setup_command: str) -> None:
    with SessionLocal() as session:
        row = session.query(Task).filter(Task.id == tid).first()
        if row:
            row.name = name.strip()
            row.command = command.strip()
            row.setup_command = setup_command.strip() or None
            session.commit()


def delete_task(tid: str) -> None:
    with SessionLocal() as session:
        row = session.query(Task).filter(Task.id == tid).first()
        if row:
            session.delete(row)
            session.commit()


# ── Triggers ──────────────────────────────────────────────────────────────────

def get_all_triggers() -> list[TriggerDTO]:
    """Used by the scheduler to load all cron triggers at startup."""
    with SessionLocal() as session:
        rows = session.query(Trigger).all()
        return [_trigger_dto(t) for t in rows]


def add_trigger(tid: str, trigger_type: str, config: dict) -> int:
    with SessionLocal() as session:
        t = Trigger(task_id=tid, trigger_type=trigger_type, config=config)
        session.add(t)
        session.commit()
        return t.id


def delete_trigger(trigger_id: int) -> None:
    with SessionLocal() as session:
        row = session.query(Trigger).filter(Trigger.id == trigger_id).first()
        if row:
            session.delete(row)
            session.commit()


# ── Build history ─────────────────────────────────────────────────────────────

def create_build(tid: str) -> int:
    """Insert a 'running' record and return its id."""
    with SessionLocal() as session:
        b = BuildHistory(
            task_id=tid,
            start_time=datetime.datetime.utcnow(),
            status="running",
        )
        session.add(b)
        session.commit()
        return b.id


def finish_build(build_id: int, status: str, output: str) -> None:
    with SessionLocal() as session:
        row = session.query(BuildHistory).filter(BuildHistory.id == build_id).first()
        if row:
            row.end_time = datetime.datetime.utcnow()
            row.status = status
            row.output_log = output
            session.commit()


def get_build(build_id: int) -> Optional[BuildDTO]:
    with SessionLocal() as session:
        row = session.query(BuildHistory).filter(BuildHistory.id == build_id).first()
        return _build_dto(row) if row else None
