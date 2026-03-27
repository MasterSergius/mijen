from nicegui import ui
from mijen.ui.theme import frame
from mijen import storage


def _sidebar_list():
    ui.label("PROJECTS").classes("text-xs font-bold p-4 text-slate-400")
    ui.button(
        "Add New Project",
        icon="add",
        on_click=lambda: ui.navigate.to("/projects/create"),
    ).props("flat").classes("w-full justify-start")
    ui.button(
        "Back to Home", icon="arrow_back", on_click=lambda: ui.navigate.to("/")
    ).props("flat").classes("w-full justify-start")


def _sidebar_detail(pid: str):
    ui.label("PROJECT MENU").classes("text-xs font-bold p-4 text-slate-400")
    ui.button("Add New Task", icon="playlist_add").props("flat").classes(
        "w-full justify-start"
    )
    ui.button("Build History", icon="history").props("flat").classes(
        "w-full justify-start"
    )
    ui.separator()
    ui.button(
        "Back to List", icon="arrow_back", on_click=lambda: ui.navigate.to("/projects")
    ).props("flat").classes("w-full justify-start")


def _sidebar_task(pid: str, tid: str):
    ui.label("TASK MENU").classes("text-xs font-bold p-4 text-slate-400")
    ui.button("Task Setup", icon="settings").props("flat").classes(
        "w-full justify-start"
    )
    ui.button("Delete Task", icon="delete", color="red").props("flat").classes(
        "w-full justify-start"
    )
    ui.separator()
    ui.button(
        "Back to Project",
        icon="arrow_back",
        on_click=lambda: ui.navigate.to(f"/projects/{pid}"),
    ).props("flat").classes("w-full justify-start")


# --- Public View Functions ---


def list_content():
    """Displays all available projects"""
    with frame("All Projects", custom_sidebar=_sidebar_list):
        ui.label("Projects").classes("text-h4 mb-4")
        with ui.row().classes("w-full gap-4"):
            for project in storage.get_all_projects():
                with (
                    ui.card()
                    .classes("w-64 cursor-pointer hover:bg-slate-100")
                    .on("click", lambda p=project.pid: ui.navigate.to(f"/projects/{p}"))
                ):
                    ui.label(project.name).classes("text-lg font-bold")
                    ui.label(f"{len(project.tasks)} Tasks").classes(
                        "text-xs text-slate-500"
                    )


def detail_content(pid: str):
    """Displays tasks for a specific project"""
    project = storage.get_project(pid)
    if not project:
        ui.navigate.to("/projects")
        return

    with frame(f"Project: {project.name}", custom_sidebar=lambda: _sidebar_detail(pid)):
        ui.label(project.name).classes("text-h4 mb-2")
        ui.label(f"Repository: {project.url}").classes("text-sm text-slate-500 mb-6")

        ui.label("Tasks").classes("text-h6 mb-2")
        with ui.column().classes("w-full gap-2"):
            for tid, task in project.tasks.items():
                with (
                    ui.card()
                    .classes("w-full cursor-pointer hover:bg-slate-50")
                    .on(
                        "click",
                        lambda p=pid, t=tid: ui.navigate.to(f"/projects/{p}/tasks/{t}"),
                    )
                ):
                    with ui.row().classes("items-center w-full justify-between"):
                        ui.label(task.name).classes("font-medium")
                        ui.icon("chevron_right")


def task_content(pid: str, tid: str):
    """Displays details/logs for a specific task"""
    project = storage.get_project(pid)
    task = project.tasks[tid] if project else None

    if not task:
        ui.navigate.to(f"/projects/{pid}")
        return

    with frame(f"Task: {task.name}", custom_sidebar=lambda: _sidebar_task(pid, tid)):
        ui.label(task.name).classes("text-h4 mb-4")
        with ui.card().classes("w-full p-4 bg-slate-50"):
            ui.label("Command to execute:").classes("text-xs font-bold text-slate-400")
            ui.code(task.command).classes("w-full")
