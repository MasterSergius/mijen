import datetime
from sqlalchemy import Column, String, ForeignKey, Text, DateTime, JSON, Integer
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)

    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    # Make 'id' the ONLY primary key
    id = Column(String, primary_key=True)

    # This is still a foreign key, but NO LONGER a primary key
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)

    name = Column(String, nullable=False)
    command = Column(Text, nullable=False)

    project = relationship("Project", back_populates="tasks")
    triggers = relationship(
        "Trigger", back_populates="task", cascade="all, delete-orphan"
    )
    history = relationship(
        "BuildHistory", back_populates="task", cascade="all, delete-orphan"
    )


class Trigger(Base):
    __tablename__ = "triggers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("tasks.id"))

    # 'cron' (schedule), 'webhook' (PR), 'checksum' (local repo)
    trigger_type = Column(String, nullable=False)

    # Store trigger config (e.g., {"cron": "0 * * * *"} or {"path": "/src"})
    # JSON is perfect for different trigger needs
    config = Column(JSON, nullable=True)

    task = relationship("Task", back_populates="triggers")


class BuildHistory(Base):
    __tablename__ = "build_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("tasks.id"))

    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    status = Column(String)  # 'Success', 'Failed', 'Running'
    output_log = Column(Text, nullable=True)  # The console output

    task = relationship("Task", back_populates="history")
