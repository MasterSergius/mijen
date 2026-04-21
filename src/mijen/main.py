import hmac
import os
import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from nicegui import app, ui

from mijen import runner, scheduler, storage
from mijen.ui.pages import home, projects, setup

# ── Optional HTTP Basic Auth ───────────────────────────────────────────────────
_AUTH_USER = os.getenv("MIJEN_AUTH_USER", "")
_AUTH_PASS = os.getenv("MIJEN_AUTH_PASS", "")
_auth_enabled = bool(_AUTH_USER and _AUTH_PASS)
_http_basic = HTTPBasic(auto_error=False)


def _check_auth(credentials: HTTPBasicCredentials = Depends(_http_basic)):
    if not _auth_enabled:
        return
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
        )
    ok_user = secrets.compare_digest(credentials.username.encode(), _AUTH_USER.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), _AUTH_PASS.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
        )


# ── Webhook endpoint ───────────────────────────────────────────────────────────
_WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


@app.post("/webhook/{tid}")
async def webhook(tid: str, request: Request):
    """
    Trigger a task run via HTTP POST.
    Protect with WEBHOOK_SECRET env var; pass it in X-Webhook-Secret header.
    """
    if _WEBHOOK_SECRET:
        token = request.headers.get("X-Webhook-Secret", "")
        if not hmac.compare_digest(token.encode(), _WEBHOOK_SECRET.encode()):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

    task = storage.get_task(tid)
    if task is None:
        return JSONResponse({"error": "task not found"}, status_code=404)

    build_id = runner.run_task(tid)
    return JSONResponse({"status": "triggered", "build_id": build_id})


# ── UI pages ──────────────────────────────────────────────────────────────────

@ui.page("/", dependencies=[Depends(_check_auth)])
def index():
    home.content()


@ui.page("/projects", dependencies=[Depends(_check_auth)])
def page_projects_list():
    projects.list_content()


@ui.page("/projects/create", dependencies=[Depends(_check_auth)])
def page_project_create():
    projects.create_content()


@ui.page("/projects/{pid}", dependencies=[Depends(_check_auth)])
def page_project_detail(pid: str):
    projects.detail_content(pid)


@ui.page("/projects/{pid}/tasks/{tid}", dependencies=[Depends(_check_auth)])
def page_task_detail(pid: str, tid: str):
    projects.task_content(pid, tid)


@ui.page("/setup", dependencies=[Depends(_check_auth)])
def setup_page():
    setup.content()


# ── Startup / shutdown ────────────────────────────────────────────────────────

app.on_startup(scheduler.init)
app.on_shutdown(scheduler.shutdown)

storage.init_db()

ui.run(
    title="MiJen",
    port=8080,
    host="0.0.0.0",
    reload=False,
    show=False,
)
