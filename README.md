# TaskPulse

TaskPulse is a small Python and JavaScript starter project. It pairs a standard-library Python API with a vanilla JavaScript frontend so you can run a full-stack kanban task board without installing a framework first.

## Features

- Python HTTP API with health checks, task CRUD, stats, export/import, NLP parse, activity feed, undo, and OpenAPI docs.
- Kanban board with To Do, Doing, and Done columns plus drag-and-drop or status buttons.
- Task due dates, tags, sprints, dependencies (`blocked_by`), recurrence, inline title editing, and filters.
- Natural language quick add: `high priority api task for Seb due Friday 30 min #backend`.
- Time tracking per task with start/stop timer on cards (separate from Pomodoro).
- Pomodoro timer per task with countdown overlay and browser notifications.
- Focus mode fullscreen overlay for one-task-at-a-time deep work.
- Activity feed showing the last 50 task events with timestamps.
- Task templates (Bug fix, Feature, Meeting, Review) plus custom templates in `localStorage`.
- Undo last 10 mutating actions via API or header button.
- Weekly review panel for overdue, stale doing, and untagged high-priority tasks.
- Keyboard shortcuts: `n`, `/`, `1/2/3`, `?`, `f`, `Esc`.
- Burndown chart showing pending task trend over the last 7 days.
- JSON file persistence by default, with optional SQLite storage.
- WebSocket live sync and presence ("Desk Fox", "Paper Owl", etc.).
- CLI: `python -m taskpulse.cli add|list|done|stats`.
- Optional API key protection for mutating routes.
- Browser UI with search, stats dashboard, dark mode, and export/import buttons.
- Shared task-shaping logic covered by Node's built-in test runner.
- Python unit tests using the standard `unittest` module.
- GitHub Actions CI and a Docker image for deployment.

## Project Structure

```text
.
├── src/taskpulse/        Python API, stores, NLP, CLI, and WebSocket hub
├── tests/                Python tests
├── web/                  JavaScript frontend
├── data/                 Runtime task persistence (gitignored)
├── openapi.yaml          API specification
├── Dockerfile            Container image
├── package.json          JavaScript test scripts
├── pyproject.toml        Python project metadata
└── Makefile              Convenience commands
```

## Run Locally

```bash
make run
```

Then open [http://localhost:8000](http://localhost:8000).

You can also run the server directly:

```bash
PYTHONPATH=src python3 -m taskpulse.server
```

Tasks are loaded from `data/tasks.json` on startup by default. If the file does not exist, default sample tasks are created and saved automatically. Recurring tasks are auto-cloned when their period has elapsed.

### Storage driver

Use the `STORAGE_DRIVER` environment variable to switch persistence:

```bash
STORAGE_DRIVER=sqlite PYTHONPATH=src python3 -m taskpulse.server
```

SQLite data is stored at `data/tasks.db`.

### API key auth

Set `API_KEY` to require an `X-API-Key` header on `POST`, `PATCH`, `DELETE`, and import routes. `GET` routes remain public. The browser prompts for a key when a mutation receives `401`.

### CLI

```bash
PYTHONPATH=src python3 -m taskpulse.cli add "Ship release" --owner Seb --priority high
PYTHONPATH=src python3 -m taskpulse.cli list
PYTHONPATH=src python3 -m taskpulse.cli done 3
PYTHONPATH=src python3 -m taskpulse.cli stats
```

## Docker

```bash
docker build -t taskpulse .
docker run --rm -p 8000:8000 taskpulse
```

## Run Tests

```bash
make test
```

Or run each side separately:

```bash
make py-test
make js-test
```

## API

```text
GET    /api/health
GET    /api/openapi
GET    /api/tasks
GET    /api/tasks/export
GET    /api/stats
GET    /api/activity
POST   /api/tasks
POST   /api/tasks/parse
POST   /api/tasks/import
POST   /api/undo
PATCH  /api/tasks/{id}
DELETE /api/tasks/{id}
WS     /ws
```

Example task payload:

```json
{
  "title": "Plan the next release",
  "owner": "Seb",
  "priority": "high",
  "minutes": 30,
  "status": "todo",
  "due_date": "2026-07-10",
  "tags": ["release", "planning"],
  "blocked_by": [2],
  "recurrence": "weekly",
  "sprint": "Sprint 12",
  "actual_minutes": 0,
  "started_at": null
}
```

Natural language parse (does not create a task):

```bash
curl -X POST http://localhost:8000/api/tasks/parse \
  -H 'Content-Type: application/json' \
  -d '{"text":"high priority api task for Seb due Friday 30 min #backend"}'
```

`PATCH /api/tasks/{id}` with an empty body toggles the task's done state. Send a JSON body to update specific fields (`title`, `owner`, `priority`, `minutes`, `done`, `status`, `due_date`, `tags`, `blocked_by`, `recurrence`, `sprint`, `actual_minutes`, `started_at`). Tasks with incomplete blockers cannot move to `doing`.

`POST /api/tasks/import` replaces all tasks with a JSON array. `GET /api/tasks/export` downloads the current task list.

`GET /api/activity` returns the last 50 activity events. `POST /api/undo` reverts the most recent mutating action.

WebSocket clients connect to `/ws` and receive:

- `{"event":"tasks_changed"}` after mutations
- `{"event":"presence_changed","clerks":["Desk Fox","Paper Owl"]}` on connect/disconnect

Stats response shape:

```json
{
  "stats": {
    "total": 3,
    "completed": 1,
    "pending": 2,
    "minutes_by_priority": {
      "high": 35,
      "medium": 25,
      "low": 15
    },
    "estimated_minutes": 75,
    "actual_minutes": 20,
    "by_sprint": {
      "Sprint 12": {
        "total": 2,
        "completed": 1,
        "pending": 1,
        "estimated_minutes": 55,
        "actual_minutes": 20
      }
    }
  }
}
```

### Keyboard shortcuts (browser UI)

| Key | Action |
|-----|--------|
| `n` | Focus new task form |
| `/` | Focus search |
| `1` / `2` / `3` | Filter To Do / Doing / Done columns |
| `f` | Enter focus mode |
| `?` | Show shortcuts modal |
| `Esc` | Close overlays |

OpenAPI is available at [http://localhost:8000/api/openapi](http://localhost:8000/api/openapi).