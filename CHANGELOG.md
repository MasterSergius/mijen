# Changelog

All notable changes to MiJen are documented here.

---

## [0.2.0] — 2026-04-21

### Added
- **System packages per project** — space-separated apt packages defined on the project; installed via `apt-get` before every task run, shared across all tasks in the project
- **Setup command per task** — optional shell script that runs in the workspace before the main command; useful for dependency installation steps
- **Directory browser for local projects** — when creating a project with source type "Local path", a modal browser lets you navigate and select a directory under `/mnt/projects` instead of typing the path manually
- **Live build history** — the history table on the task page refreshes automatically when a build completes, no page reload needed
- **Build log dialog** — clicking any row in the build history table opens a dialog with the full log output, status badge, start time, and duration
- **Edit task** — command, setup command, and name can be edited from the task detail page without deleting and recreating
- **Edit system packages** — system packages can be updated from the project detail page

### Changed
- `make` and `git` are pre-installed in the container image as universal build tools

### Fixed
- `ui.slot` replaced with `table.add_slot()` — status badges in the history table now render correctly

---

## [0.1.0] — 2026-04-19

### Added
- **Project management** — create, view, and delete projects with two source types: GitHub URL and local path
- **GitHub source** — repos are cloned with `--depth=1` on first run and updated with `git pull --ff-only` on subsequent runs
- **Local source** — host directories mounted via `LOCAL_PROJECTS_DIR` env var are browsable at `/mnt/projects` inside the container
- **Task management** — create, view, edit, and delete tasks with shell commands; multiple tasks per project
- **Live log streaming** — build output streamed to the UI in real time via a background thread + polling timer
- **Cron triggers** — schedule task runs with standard 5-field UTC cron expressions via APScheduler
- **Webhook triggers** — trigger task runs via `POST /webhook/<task-id>`; protected by `X-Webhook-Secret` header
- **Build history** — each run stored in the database with status, start time, end time, and full log output
- **Optional HTTP Basic Auth** — UI protected by `MIJEN_AUTH_USER` / `MIJEN_AUTH_PASS` env vars
- **PostgreSQL backend** — via SQLAlchemy with a DTO pattern to prevent session leaks
- **Automatic schema migrations** — `init_db()` applies incremental `ALTER TABLE` changes at startup using PostgreSQL `IF NOT EXISTS` / `IF EXISTS` syntax; safe to run on every restart
- **Docker Compose setup** — `mijen` and `db` services with Postgres health check and `depends_on: condition: service_healthy`
- **Makefile** — `up`, `down`, `build`, `rebuild`, `restart`, `reset`, `logs`, `logs-app`, `logs-db`, `ps`, `shell`, `clean`
- **`.env.example`** — template with all supported variables and descriptions
