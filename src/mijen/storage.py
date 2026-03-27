import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from mijen.models import Base, Project, Task

# Fallback to sqlite for local dev if the variable isn't set
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./mijen.db")
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_all_projects():
    with SessionLocal() as session:
        return session.query(Project).all()


def get_project(pid: str):
    with SessionLocal() as session:
        return session.query(Project).filter(Project.id == pid).first()


def add_project(pid: str, name: str, url: str):
    with SessionLocal() as session:
        new_project = Project(id=pid, name=name, url=url)
        session.add(new_project)
        session.commit()
        return pid


def add_task(pid: str, tid: str, name: str, command: str):
    with SessionLocal() as session:
        new_task = Task(id=tid, project_id=pid, name=name, command=command)
        session.add(new_task)
        session.commit()
        return tid
