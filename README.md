# TaskPulse

TaskPulse is a small Python and JavaScript starter project. It pairs a standard-library Python API with a vanilla JavaScript frontend so you can run a full-stack kanban task board without installing a framework first.

## Features

- Python HTTP API with health checks, task CRUD, stats, export/import, and OpenAPI docs.
- Kanban board with To Do, Doing, and Done columns plus drag-and-drop or status buttons.
- Task due dates, tags, inline title editing, and filters for tag and due today.
- JSON file persistence by default, with optional SQLite storage.
- WebSocket live sync so connected clients refresh after mutations.
- Optional API key protection for mutating routes.
- Browser UI with search, stats dashboard, dark mode, and export/import buttons.
- Shared task-shaping logic covered by Node's built-in test runner.
- Python unit tests using the standard `unittest` module.
- GitHub Actions CI and a Docker image for deployment.

## Project Structure

```text
.
├── src/taskpulse/        Python API, stores, and WebSocket hub
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

Tasks are loaded from `data/tasks.json` on startup by default. If the file does not exist, default sample tasks are created and saved automatically.

### Storage driver

Use the `STORAGE_DRIVER` environment variable to switch persistence:

```bash
STORAGE_DRIVER=sqlite PYTHONPATH=src python3 -m taskpulse.server
```

SQLite data is stored at `data/tasks.db`.

### API key auth

Set `API_KEY` to require an `X-API-Key` header on `POST`, `PATCH`, `DELETE`, and import routes. `GET` routes remain public. The browser prompts for a key when a mutation receives `401`.

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
POST   /api/tasks
POST   /api/tasks/import
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
  "tags": ["release", "planning"]
}
```

`PATCH /api/tasks/{id}` with an empty body toggles the task's done state. Send a JSON body to update specific fields (`title`, `owner`, `priority`, `minutes`, `done`, `status`, `due_date`, `tags`).

`POST /api/tasks/import` replaces all tasks with a JSON array. `GET /api/tasks/export` downloads the current task list.

WebSocket clients connect to `/ws` and receive `{"event":"tasks_changed"}` after mutations.

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
    }
  }
}
```

OpenAPI is available at [http://localhost:8000/api/openapi](http://localhost:8000/api/openapi).