"""
All project/task UI pages.

Pages:
  list_content()         — /projects
  create_content()       — /projects/create
  detail_content(pid)    — /projects/{pid}
  task_content(pid, tid) — /projects/{pid}/tasks/{tid}
"""
import os
import re
from pathlib import Path
from nicegui import ui
from mijen import runner, scheduler, storage
from mijen.ui.theme import frame

LOCAL_PROJECTS_ROOT = Path(os.getenv("LOCAL_PROJECTS_DIR", "/tmp/mijen-local-projects"))
# Inside the container the host dir is always mounted here
_MOUNT_POINT = Path("/mnt/projects")

# Very permissive URL check — just prevents obviously wrong input
_GITHUB_RE = re.compile(r"^https?://[^\s]+\.git$|^https?://github\.com/[^\s]+$")


# ── Sidebars ──────────────────────────────────────────────────────────────────

def _sidebar_list():
    ui.label("PROJECTS").classes("text-xs font-bold p-4 text-slate-400")
    ui.button("New Project", icon="add",
              on_click=lambda: ui.navigate.to("/projects/create")
              ).props("flat").classes("w-full justify-start")
    ui.separator()
    ui.button("Home", icon="home",
              on_click=lambda: ui.navigate.to("/")
              ).props("flat").classes("w-full justify-start")


def _sidebar_detail(pid: str):
    ui.label("PROJECT").classes("text-xs font-bold p-4 text-slate-400")
    ui.button("Back to list", icon="arrow_back",
              on_click=lambda: ui.navigate.to("/projects")
              ).props("flat").classes("w-full justify-start")


def _sidebar_task(pid: str, tid: str):
    ui.label("TASK").classes("text-xs font-bold p-4 text-slate-400")
    ui.button("Back to project", icon="arrow_back",
              on_click=lambda: ui.navigate.to(f"/projects/{pid}")
              ).props("flat").classes("w-full justify-start")


# ── Project list ──────────────────────────────────────────────────────────────

def list_content():
    with frame("Projects", custom_sidebar=_sidebar_list):
        ui.label("Projects").classes("text-h4 mb-4")
        all_projects = storage.get_all_projects()
        if not all_projects:
            ui.label("No projects yet.").classes("text-slate-400")
            ui.button("Create your first project", icon="add",
                      on_click=lambda: ui.navigate.to("/projects/create"))
            return

        with ui.row().classes("w-full flex-wrap gap-4"):
            for p in all_projects:
                with (
                    ui.card()
                    .classes("w-64 cursor-pointer hover:shadow-md transition-shadow")
                    .on("click", lambda pid=p.id: ui.navigate.to(f"/projects/{pid}"))
                ):
                    with ui.row().classes("items-center gap-2 mb-1"):
                        icon = "cloud" if p.source_type == "github" else "folder"
                        ui.icon(icon).classes("text-slate-400")
                        ui.label(p.name).classes("text-lg font-bold")
                    ui.label(f"{len(p.tasks)} task(s)").classes("text-xs text-slate-500")
                    ui.label(p.source).classes("text-xs text-slate-400 truncate w-full")


# ── Directory browser dialog ──────────────────────────────────────────────────

def _open_dir_browser(label_el, path_input):
    """
    Modal directory browser rooted at /mnt/projects.
    When the user confirms a selection, writes the chosen path into
    path_input and updates label_el with the display name.
    """
    root = _MOUNT_POINT
    state = {"path": root}

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Select project folder").classes("text-h6 p-4 pb-0")
        path_label = ui.label(str(root)).classes(
            "text-xs text-slate-500 px-4 pb-2 truncate w-full"
        )
        dir_list = ui.column().classes("w-full px-2 overflow-y-auto").style("max-height:320px")
        select_btn_label = ui.label("").classes("text-xs text-slate-400 px-4 truncate w-full")

        def refresh(path: Path):
            state["path"] = path
            path_label.text = str(path)
            select_btn_label.text = f"Will select: {path}"
            dir_list.clear()
            with dir_list:
                up_btn = ui.button(
                    ".. (go up)", icon="arrow_upward",
                    on_click=lambda: refresh(state["path"].parent),
                ).props("flat dense align=left").classes("w-full justify-start text-slate-500")
                up_btn.set_enabled(path != root)

                try:
                    entries = sorted(
                        (e for e in path.iterdir() if e.is_dir() and not e.name.startswith(".")),
                        key=lambda e: e.name.lower(),
                    )
                except PermissionError:
                    ui.label("Permission denied").classes("text-red-500 text-sm p-2")
                    return

                if not entries:
                    ui.label("(no subdirectories)").classes("text-slate-400 text-sm p-2")
                else:
                    for entry in entries:
                        ui.button(
                            entry.name, icon="folder",
                            on_click=lambda e=entry: refresh(e),
                        ).props("flat dense align=left").classes(
                            "w-full justify-start font-mono text-sm"
                        )

        refresh(root)

        def _select():
            chosen = state["path"]
            path_input.value = str(chosen)
            label_el.text = str(chosen)
            dialog.close()

        with ui.row().classes("gap-2 justify-end p-4 pt-2 w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Select this folder", icon="check", on_click=_select)

    dialog.open()


# ── Project creation ──────────────────────────────────────────────────────────

def create_content():
    with frame("New Project", custom_sidebar=_sidebar_list):
        ui.label("Create Project").classes("text-h4 mb-6")

        with ui.card().classes("w-full max-w-lg p-6"):
            name_input = ui.input(
                "Project name",
                placeholder="My cool project",
                validation={"Required": lambda v: bool(v.strip()),
                            "Max 100 chars": lambda v: len(v) <= 100},
            ).classes("w-full mb-4")

            source_type = {"value": "github"}
            ui.label("Source type").classes("text-sm text-slate-500 mb-1")
            with ui.row().classes("gap-4 mb-4"):
                ui.radio(
                    {"github": "GitHub URL", "local": "Local path"},
                    value="github",
                    on_change=lambda e: _on_source_type_change(e.value),
                ).props("inline")

            # GitHub URL input (shown by default)
            github_row = ui.row().classes("w-full mb-4")
            with github_row:
                source_input = ui.input(
                    "GitHub URL",
                    placeholder="https://github.com/user/repo",
                ).classes("w-full")

            # Local path picker (hidden until "local" is selected)
            local_row = ui.column().classes("w-full mb-4").style("display:none")
            with local_row:
                with ui.row().classes("w-full items-center gap-2"):
                    local_label = ui.label("No folder selected").classes(
                        "text-sm text-slate-500 flex-1 truncate"
                    )
                    ui.button("Browse…", icon="folder_open",
                              on_click=lambda: _open_dir_browser(local_label, source_input)
                              ).props("flat dense")

            def _on_source_type_change(val: str):
                source_type["value"] = val
                github_row.style("display:flex" if val == "github" else "display:none")
                local_row.style("display:block" if val == "local" else "display:none")
                source_input.value = ""
                if val == "local":
                    local_label.text = "No folder selected"

            def _validate_source(v: str) -> str | None:
                v = v.strip()
                if not v:
                    return "Required"
                if source_type["value"] == "github":
                    if not _GITHUB_RE.match(v):
                        return "Enter a valid GitHub URL"
                return None

            ui.separator().classes("my-2")
            packages_input = ui.input(
                "System packages (optional)",
                placeholder="cmake g++ ninja-build",
            ).classes("w-full mb-2")
            ui.label("Space-separated apt packages installed before every task run.") \
              .classes("text-xs text-slate-400 mb-4")

            error_label = ui.label("").classes("text-red-500 text-sm mb-4")

            def _submit():
                name = name_input.value.strip()
                source = source_input.value.strip()
                err = _validate_source(source)
                if not name:
                    error_label.text = "Project name is required"
                    return
                if err:
                    error_label.text = err
                    return
                error_label.text = ""
                try:
                    pid = storage.create_project(
                        name=name,
                        source_type=source_type["value"],
                        source=source,
                        system_packages=packages_input.value,
                    )
                except Exception as e:
                    error_label.text = f"Error: {e}"
                    return
                ui.navigate.to(f"/projects/{pid}")

            ui.button("Create Project", icon="check", on_click=_submit).classes("w-full")


# ── Project detail ────────────────────────────────────────────────────────────

def detail_content(pid: str):
    project = storage.get_project(pid)
    if project is None:
        ui.navigate.to("/projects")
        return

    with frame(f"Project: {project.name}", custom_sidebar=lambda: _sidebar_detail(pid)):
        with ui.row().classes("w-full justify-between items-center mb-2"):
            ui.label(project.name).classes("text-h4")
            ui.button("Delete project", icon="delete", color="negative",
                      on_click=lambda: _confirm_delete_project(pid)
                      ).props("flat")

        with ui.row().classes("items-center gap-2 mb-6 text-slate-500 text-sm"):
            icon = "cloud" if project.source_type == "github" else "folder"
            ui.icon(icon)
            ui.label(project.source)

        # ── System packages ──
        with ui.card().classes("w-full p-4 mb-6"):
            with ui.row().classes("w-full justify-between items-center mb-2"):
                ui.label("System packages").classes("text-xs font-bold text-slate-400")
                ui.button("Edit", icon="edit",
                          on_click=lambda: _open_packages_dialog(pid)
                          ).props("flat dense")
            pkg_text = project.system_packages or "(none)"
            ui.label(pkg_text).classes("font-mono text-sm")

        # ── Task list ──
        with ui.row().classes("w-full justify-between items-center mb-2"):
            ui.label("Tasks").classes("text-h6")
            ui.button("Add task", icon="add",
                      on_click=lambda: _open_add_task_dialog(pid)
                      ).props("flat")

        task_area = ui.column().classes("w-full gap-2")
        _render_tasks(task_area, pid, project.tasks)


def _render_tasks(container, pid: str, tasks):
    container.clear()
    with container:
        if not tasks:
            ui.label("No tasks yet.").classes("text-slate-400")
            return
        for task in tasks:
            with (
                ui.card()
                .classes("w-full cursor-pointer hover:bg-slate-50")
                .on("click", lambda p=pid, t=task.id: ui.navigate.to(f"/projects/{p}/tasks/{t}"))
            ):
                with ui.row().classes("items-center w-full justify-between"):
                    ui.label(task.name).classes("font-medium")
                    ui.icon("chevron_right").classes("text-slate-400")


def _open_packages_dialog(pid: str):
    project = storage.get_project(pid)
    with ui.dialog() as dialog, ui.card().classes("w-96 p-6"):
        ui.label("System packages").classes("text-h6 mb-1")
        ui.label("Space-separated apt packages installed before every task run.") \
          .classes("text-xs text-slate-400 mb-3")
        pkg_in = ui.input(
            "Packages",
            value=project.system_packages or "",
            placeholder="cmake g++ ninja-build",
        ).classes("w-full mb-4")

        def _save():
            storage.update_project_packages(pid, pkg_in.value)
            dialog.close()
            ui.navigate.to(f"/projects/{pid}")

        with ui.row().classes("gap-3 justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Save", icon="check", on_click=_save)

    dialog.open()


def _open_add_task_dialog(pid: str):
    with ui.dialog() as dialog, ui.card().classes("w-96 p-6"):
        ui.label("New Task").classes("text-h6 mb-4")

        name_in = ui.input(
            "Task name",
            placeholder="Run tests",
            validation={"Required": lambda v: bool(v.strip()),
                        "Max 100 chars": lambda v: len(v) <= 100},
        ).classes("w-full mb-3")

        cmd_in = ui.textarea(
            "Command",
            placeholder="pytest --tb=short",
            validation={"Required": lambda v: bool(v.strip()),
                        "Max 4000 chars": lambda v: len(v) <= 4000},
        ).classes("w-full mb-3").props("rows=4")

        ui.separator().classes("my-2")
        setup_in = ui.textarea(
            "Setup command (optional)",
            placeholder="pip install -r requirements.txt",
        ).classes("w-full mb-1").props("rows=3")
        ui.label("Runs before the main command, in the project workspace.") \
          .classes("text-xs text-slate-400 mb-4")

        err = ui.label("").classes("text-red-500 text-sm mb-3")

        def _save():
            n = name_in.value.strip()
            c = cmd_in.value.strip()
            if not n or not c:
                err.text = "Both fields are required"
                return
            storage.create_task(pid, n, c, setup_command=setup_in.value)
            dialog.close()
            ui.navigate.to(f"/projects/{pid}")   # refresh

        with ui.row().classes("gap-3 justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Save", icon="check", on_click=_save)

    dialog.open()


def _confirm_delete_project(pid: str):
    with ui.dialog() as dialog, ui.card().classes("p-6"):
        ui.label("Delete this project and all its tasks?").classes("text-h6 mb-4")
        with ui.row().classes("gap-3 justify-end"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Delete", color="negative", on_click=lambda: _do_delete_project(pid, dialog))
    dialog.open()


def _do_delete_project(pid: str, dialog):
    dialog.close()
    storage.delete_project(pid)
    ui.navigate.to("/projects")


def _open_build_dialog(build_id: int):
    build = storage.get_build(build_id)
    if build is None:
        return
    start = build.start_time.strftime("%Y-%m-%d %H:%M:%S") if build.start_time else "—"
    if build.start_time and build.end_time:
        dur = f"{int((build.end_time - build.start_time).total_seconds())}s"
    else:
        dur = "—"
    color = "text-green-600" if build.status == "success" else \
            "text-red-600"   if build.status == "failed"  else "text-yellow-600"

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-3xl p-6"):
        with ui.row().classes("w-full justify-between items-center mb-1"):
            ui.label(f"Build #{build_id}").classes("text-h6")
            ui.button(icon="close", on_click=dialog.close).props("flat dense")
        with ui.row().classes("gap-6 text-sm text-slate-500 mb-4"):
            ui.label(f"Started: {start}")
            ui.label(f"Duration: {dur}")
            ui.label(build.status).classes(f"font-bold {color}")

        log_el = ui.log(max_lines=2000).classes("w-full font-mono text-sm").style("height:480px")
        if build.output_log:
            for line in build.output_log.splitlines():
                log_el.push(line)
        else:
            log_el.push("(no output)")

    dialog.open()


# ── Task detail ───────────────────────────────────────────────────────────────

def task_content(pid: str, tid: str):
    task = storage.get_task(tid)
    if task is None:
        ui.navigate.to(f"/projects/{pid}")
        return

    project = storage.get_project(pid)

    with frame(f"Task: {task.name}", custom_sidebar=lambda: _sidebar_task(pid, tid)):
        with ui.row().classes("w-full justify-between items-center mb-4"):
            ui.label(task.name).classes("text-h4")
            ui.button("Delete task", icon="delete", color="negative",
                      on_click=lambda: _confirm_delete_task(pid, tid)
                      ).props("flat")

        # ── Command card ──
        with ui.card().classes("w-full p-4 mb-6"):
            with ui.row().classes("w-full justify-between items-center mb-2"):
                ui.label("Command").classes("text-xs font-bold text-slate-400")
                ui.button("Edit", icon="edit",
                          on_click=lambda: _open_edit_task_dialog(pid, tid)
                          ).props("flat dense")
            if task.setup_command:
                ui.label("Setup command").classes("text-xs text-slate-400 mb-1")
                ui.code(task.setup_command, language="bash").classes("w-full mb-3")
                ui.label("Main command").classes("text-xs text-slate-400 mb-1")
            ui.code(task.command, language="bash").classes("w-full")

        # ── Run section ──
        ui.label("Build").classes("text-h6 mb-2")
        with ui.card().classes("w-full p-4 mb-6"):
            current_build: dict = {"id": None}
            status_label = ui.label("").classes("text-sm text-slate-500 mb-2")
            log_el = ui.log(max_lines=500).classes("w-full h-64 font-mono text-sm")

            async def _poll():
                bid = current_build["id"]
                if bid is None:
                    return
                for line in runner.drain_lines(bid):
                    log_el.push(line)
                if not runner.is_running(bid):
                    build = storage.get_build(bid)
                    if build:
                        color = "text-green-600" if build.status == "success" else "text-red-600"
                        status_label.classes(color, remove="text-slate-500 text-yellow-600")
                        status_label.text = f"Status: {build.status}"
                    poll_timer.active = False
                    runner.cleanup(bid)
                    current_build["id"] = None
                    history_table.refresh()  # update history without page reload

            poll_timer = ui.timer(0.5, _poll, active=False)

            def _run():
                log_el.clear()
                status_label.text = "Running…"
                status_label.classes("text-yellow-600", remove="text-green-600 text-red-600 text-slate-500")
                bid = runner.run_task(tid)
                if bid < 0:
                    status_label.text = "Error: could not start build"
                    return
                current_build["id"] = bid
                poll_timer.active = True

            ui.button("▶ Run now", on_click=_run).classes("mb-3")

        # ── Triggers ──
        ui.label("Triggers").classes("text-h6 mb-2")
        trigger_area = ui.column().classes("w-full gap-2 mb-6")
        _render_triggers(trigger_area, tid)

        with ui.row().classes("gap-3"):
            ui.button("+ Cron trigger", icon="schedule",
                      on_click=lambda: _open_cron_dialog(tid, trigger_area)
                      ).props("flat")
            ui.button("Webhook URL", icon="link",
                      on_click=lambda: _show_webhook_info(tid)
                      ).props("flat")

        # ── Build history ──
        ui.label("Build History").classes("text-h6 mb-2")

        @ui.refreshable
        def history_table():
            t = storage.get_task(tid)
            if not t or not t.history:
                ui.label("No builds yet.").classes("text-slate-400")
                return
            table = ui.table(
                columns=[
                    {"name": "id",     "label": "#",       "field": "id",     "align": "left"},
                    {"name": "start",  "label": "Started", "field": "start",  "align": "left"},
                    {"name": "dur",    "label": "Duration","field": "dur",    "align": "left"},
                    {"name": "status", "label": "Status",  "field": "status", "align": "left"},
                ],
                rows=[_build_row(b) for b in t.history[:50]],
            ).classes("w-full cursor-pointer")
            table.add_slot("body-cell-status", """
                <q-td :props="props">
                    <q-badge :color="props.value === 'success' ? 'green' :
                                     props.value === 'failed'  ? 'red'   : 'orange'"
                             :label="props.value" />
                </q-td>
            """)
            table.on("rowClick", lambda e: _open_build_dialog(e.args[1]["id"]))

        history_table()


def _build_row(b) -> dict:
    start = b.start_time.strftime("%Y-%m-%d %H:%M:%S") if b.start_time else "—"
    if b.start_time and b.end_time:
        secs = int((b.end_time - b.start_time).total_seconds())
        dur = f"{secs}s"
    else:
        dur = "—"
    return {"id": b.id, "start": start, "dur": dur, "status": b.status}


def _render_triggers(container, tid: str):
    container.clear()
    task = storage.get_task(tid)
    if not task or not task.triggers:
        with container:
            ui.label("No triggers configured.").classes("text-slate-400 text-sm")
        return
    with container:
        for t in task.triggers:
            with ui.row().classes("items-center gap-4"):
                if t.trigger_type == "cron":
                    ui.icon("schedule")
                    ui.label(f"Cron: {t.config.get('cron', '?')}")
                else:
                    ui.icon("link")
                    ui.label("Webhook")
                ui.button(icon="delete", color="negative",
                          on_click=lambda tid_=tid, tid_trigger=t.id, c=container:
                              _delete_trigger(tid_trigger, tid_, c)
                          ).props("flat dense")


def _delete_trigger(trigger_id: int, tid: str, container):
    storage.delete_trigger(trigger_id)
    scheduler.sync()
    _render_triggers(container, tid)


def _open_cron_dialog(tid: str, trigger_area):
    with ui.dialog() as dialog, ui.card().classes("w-96 p-6"):
        ui.label("Add Cron Trigger").classes("text-h6 mb-2")
        ui.label("Standard 5-field cron expression (UTC).").classes("text-sm text-slate-500 mb-4")
        cron_in = ui.input(
            "Cron expression",
            placeholder="0 * * * *   (every hour)",
            validation={"Required": lambda v: bool(v.strip()),
                        "Must be 5 fields": lambda v: len(v.strip().split()) == 5},
        ).classes("w-full mb-4")
        err = ui.label("").classes("text-red-500 text-sm mb-3")

        def _save():
            expr = cron_in.value.strip()
            if not expr or len(expr.split()) != 5:
                err.text = "Enter a valid 5-field cron expression"
                return
            storage.add_trigger(tid, "cron", {"cron": expr})
            scheduler.sync()
            dialog.close()
            _render_triggers(trigger_area, tid)

        with ui.row().classes("gap-3 justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Add", icon="check", on_click=_save)

    dialog.open()


def _show_webhook_info(tid: str):
    host = os.getenv("MIJEN_PUBLIC_URL", "http://localhost:8080")
    url = f"{host}/webhook/{tid}"
    secret = os.getenv("WEBHOOK_SECRET", "")

    with ui.dialog() as dialog, ui.card().classes("w-96 p-6"):
        ui.label("Webhook").classes("text-h6 mb-4")
        ui.label("POST to this URL to trigger a run:").classes("text-sm text-slate-500 mb-1")
        ui.code(url, language="text").classes("w-full mb-3")
        if secret:
            ui.label("Include this header for authentication:").classes("text-sm text-slate-500 mb-1")
            ui.code(f"X-Webhook-Secret: {secret}", language="text").classes("w-full mb-3")
        ui.button("Close", on_click=dialog.close)

    dialog.open()


def _open_edit_task_dialog(pid: str, tid: str):
    task = storage.get_task(tid)
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg p-6"):
        ui.label("Edit task").classes("text-h6 mb-4")

        name_in = ui.input(
            "Task name",
            value=task.name,
            validation={"Required": lambda v: bool(v.strip()),
                        "Max 100 chars": lambda v: len(v) <= 100},
        ).classes("w-full mb-3")

        cmd_in = ui.textarea(
            "Command",
            value=task.command,
            validation={"Required": lambda v: bool(v.strip()),
                        "Max 4000 chars": lambda v: len(v) <= 4000},
        ).classes("w-full mb-3").props("rows=4")

        ui.separator().classes("my-2")
        setup_in = ui.textarea(
            "Setup command (optional)",
            value=task.setup_command or "",
            placeholder="pip install -r requirements.txt",
        ).classes("w-full mb-1").props("rows=3")
        ui.label("Runs before the main command, in the project workspace.") \
          .classes("text-xs text-slate-400 mb-4")

        err = ui.label("").classes("text-red-500 text-sm mb-3")

        def _save():
            n = name_in.value.strip()
            c = cmd_in.value.strip()
            if not n or not c:
                err.text = "Name and command are required"
                return
            storage.update_task(tid, n, c, setup_in.value)
            dialog.close()
            ui.navigate.to(f"/projects/{pid}/tasks/{tid}")

        with ui.row().classes("gap-3 justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Save", icon="check", on_click=_save)

    dialog.open()


def _confirm_delete_task(pid: str, tid: str):
    with ui.dialog() as dialog, ui.card().classes("p-6"):
        ui.label("Delete this task and all its history?").classes("text-h6 mb-4")
        with ui.row().classes("gap-3 justify-end"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Delete", color="negative",
                      on_click=lambda: _do_delete_task(pid, tid, dialog))
    dialog.open()


def _do_delete_task(pid: str, tid: str, dialog):
    dialog.close()
    storage.delete_task(tid)
    ui.navigate.to(f"/projects/{pid}")
