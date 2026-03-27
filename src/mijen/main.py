from nicegui import ui
from mijen import storage
from mijen.ui.pages import home, projects, setup


@ui.page("/")
def index():
    home.content()


@ui.page("/projects")
def page_projects_list():
    projects.list_content()


@ui.page("/projects/{pid}")
def page_project_detail(pid: str):
    projects.detail_content(pid)


@ui.page("/projects/{pid}/tasks/{tid}")
def page_task_detail(pid: str, tid: str):
    projects.task_content(pid, tid)


@ui.page("/setup")
def setup_page():
    setup.content()


storage.init_db()  # Create tables if they don't exist
ui.run(title="MiJen", port=8080, reload=True)
