import datetime
from sqlalchemy import Column, String, ForeignKey, Text, DateTime, JSON, Integer
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True)          # UUID string
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)   # 'github' | 'local'
    source = Column(String, nullable=False)        # GitHub URL or absolute local path
    system_packages = Column(Text, nullable=True)  # space-separated apt packages

    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)          # UUID string
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    command = Column(Text, nullable=False)
    setup_command = Column(Text, nullable=True)    # runs before command, in the workspace

    project = relationship("Project", back_populates="tasks")
    triggers = relationship("Trigger", back_populates="task", cascade="all, delete-orphan")
    history = relationship(
        "BuildHistory",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="BuildHistory.start_time.desc()",
    )


class Trigger(Base):
    __tablename__ = "triggers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    trigger_type = Column(String, nullable=False)  # 'cron' | 'webhook'
    config = Column(JSON, nullable=True)           # e.g. {"cron": "0 * * * *"}

    task = relationship("Task", back_populates="triggers")


class BuildHistory(Base):
    __tablename__ = "build_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    status = Column(String, nullable=False)        # 'running' | 'success' | 'failed'
    output_log = Column(Text, nullable=True)

    task = relationship("Task", back_populates="history")
