# MiJen

Minimalist Jenkins-like automation server. Define projects, attach shell tasks, and run them on demand, on a cron schedule, or via webhook — all from a clean web UI.

- **No YAML pipelines** — commands are plain shell scripts stored in the database
- **Two source types** — GitHub URL (auto clone/pull) or local directory
- **Live log streaming** — watch build output in real time
- **Cron & webhook triggers** — schedule runs or fire them from external systems
- **Per-project system packages** — install apt dependencies once, shared across all tasks
- **Per-task setup commands** — run install steps before the main command

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/) v2

That's it.

---

## Quick start

### 1. Clone and configure

```bash
git clone https://github.com/yourname/mijen.git
cd mijen
cp .env.example .env
```

Open `.env` and fill in at minimum:

```env
POSTGRES_USER=mijen
POSTGRES_PASSWORD=your-strong-password
POSTGRES_DB=mijen
DATABASE_URL=postgresql://mijen:your-strong-password@db:5432/mijen
```

See the [full env var reference](#environment-variables-reference) below for all options.

### 2. Build and run

```bash
make build
make up
```

The web UI is available at **http://localhost:8080**.

Postgres starts first with a health check — MiJen waits for it automatically.

### 3. Stop

```bash
make down
```

---

## Creating your first project

### GitHub project

1. Click **Projects → New Project** in the sidebar
2. Enter a project name
3. Select **GitHub URL** and paste the repo URL, e.g. `https://github.com/user/repo.git`
4. Optionally add **System packages** (apt) the project needs, e.g. `cmake g++ ninja-build`
5. Click **Create Project**

On first run MiJen clones the repo with `--depth=1`. Subsequent runs do `git pull --ff-only`, so tasks always run against the latest commit.

**Example — Python project mirroring a GitHub Actions workflow:**

| GitHub Actions step | MiJen equivalent |
|---|---|
| `actions/checkout` | Automatic (git clone/pull) |
| `actions/setup-python` | Python is pre-installed in the container |
| Install deps | Task **Setup command** |
| Run tests | Task **Command** |

Task setup command:
```bash
python -m pip install --upgrade pip
make install
pip install -r test_requirements.txt
```

Task command:
```bash
make test
```

### Local project

1. Set `LOCAL_PROJECTS_DIR` in `.env` to the parent folder containing your projects on the host:
   ```env
   LOCAL_PROJECTS_DIR=/home/yourname/projects
   ```
2. Run `make rebuild` to pick up the new volume mount
3. Create a project, select **Local path**, and click **Browse…** to pick the directory — it's mounted at `/mnt/projects` inside the container

---

## Adding tasks

On the project detail page, click **Add task**:

| Field | Description |
|---|---|
| **Task name** | Human-readable label, e.g. "Run tests" |
| **Command** | Main shell script to run, e.g. `make test` |
| **Setup command** *(optional)* | Runs before the main command in the project workspace, e.g. `pip install -r requirements.txt` |

Tasks can be edited later from the task detail page.

---

## Running tasks

### Manually

Open a task and click **▶ Run now**. Output streams live to the log panel.

### Cron schedule

On the task page, click **+ Cron trigger** and enter a standard 5-field UTC cron expression:

```
0 * * * *      # every hour
30 6 * * 1-5   # 06:30 UTC on weekdays
0 2 * * *      # every night at 02:00 UTC
```

### Webhook

On the task page, click **Webhook URL** to get the endpoint and header:

```bash
curl -X POST https://your-mijen-host/webhook/<task-id> \
     -H "X-Webhook-Secret: your-secret"
```

Response:
```json
{"status": "triggered", "build_id": 42}
```

Set `WEBHOOK_SECRET` in `.env` to require the header. Leave it empty to disable authentication (not recommended for public-facing instances).

---

## Build history

The task page shows a history table with status badges that update automatically after each run. Click any row to open a dialog with the full build log, duration, and status.

---

## System packages

System packages are defined per **project** and installed via `apt-get` before any task runs. This means all tasks in a project share the same toolchain without repeating install steps.

On the project detail page, click **Edit** next to System packages and enter space-separated package names:

```
cmake g++ ninja-build qt6-base-dev
```

Packages are installed on every build run (after `apt-get update`). For large toolchains this adds a few seconds — acceptable for CI use.

---

## Inspecting the database

Shell into the Postgres container:

```bash
docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB>
```

Useful queries:

```sql
SELECT id, name, source_type, source, system_packages FROM projects;
SELECT id, name, command, setup_command FROM tasks;
SELECT id, task_id, status, start_time, end_time FROM build_history ORDER BY start_time DESC LIMIT 10;
```

---

## Makefile reference

| Target | What it does |
|---|---|
| `make up` | Start all containers in the background |
| `make down` | Stop all containers |
| `make build` | Build (or rebuild) Docker images |
| `make restart` | Rebuild images and restart everything |
| `make rebuild` | Rebuild and restart **app only** — DB keeps running, no volume wipe |
| `make reset` | **Nuclear option** — wipe all volumes and start fresh |
| `make logs` | Follow logs for all services |
| `make logs-app` | Follow app logs only |
| `make logs-db` | Follow database logs only |
| `make ps` | Show container status |
| `make shell` | Open a bash shell inside the app container |
| `make clean` | Run `docker system prune -f` |

`make rebuild` is the go-to command after any code or config change — it rebuilds only the app image and hot-swaps the container without touching the database.

---

## Updating environment variables

1. Edit `.env`
2. Apply:
```bash
make rebuild
```

---

## Wiping the database

**Destructive — all projects, tasks, triggers, and build history will be lost.**

```bash
make reset
```

---

## Logs

```bash
make logs-app    # stream app logs
make logs-db     # stream database logs
make logs        # both
```

---

## Environment variables reference

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_USER` | — | Required |
| `POSTGRES_PASSWORD` | — | Required — use a strong random string |
| `POSTGRES_DB` | — | Required |
| `DATABASE_URL` | — | Required — `postgresql://user:pass@db:5432/dbname` |
| `WEBHOOK_SECRET` | *(empty — disabled)* | Recommended for any networked instance |
| `MIJEN_AUTH_USER` | *(empty — disabled)* | HTTP Basic Auth username for the UI |
| `MIJEN_AUTH_PASS` | *(empty — disabled)* | HTTP Basic Auth password for the UI |
| `MIJEN_PUBLIC_URL` | `http://localhost:8080` | Used in webhook URL display |
| `LOCAL_PROJECTS_DIR` | *(empty)* | Host path mounted at `/mnt/projects` in the container |
| `WORKSPACES_DIR` | `/app/workspaces` | Where GitHub repos are cloned inside the container |
| `MAX_OUTPUT_BYTES` | `1000000` (1 MB) | Build log size cap — prevents runaway output |
| `BUILD_TIMEOUT_SECONDS` | `3600` (1 hour) | Hard timeout per build |
