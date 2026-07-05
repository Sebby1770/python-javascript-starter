# TaskPulse

TaskPulse is a small Python and JavaScript starter project. It pairs a standard-library Python API with a vanilla JavaScript frontend so you can run a full-stack app without installing a framework first.

## Features

- Python HTTP API with health checks, task CRUD, and stats.
- JSON file persistence at `data/tasks.json`.
- Browser UI with search, stats dashboard, dark mode, and task actions.
- Shared task-shaping logic covered by Node's built-in test runner.
- Python unit tests using the standard `unittest` module.

## Project Structure

```text
.
├── src/taskpulse/        Python API and task store
├── tests/                Python tests
├── web/                  JavaScript frontend
├── data/                 Runtime task persistence (gitignored)
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

Tasks are loaded from `data/tasks.json` on startup. If the file does not exist, default sample tasks are created and saved automatically.

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
GET    /api/tasks
GET    /api/stats
POST   /api/tasks
PATCH  /api/tasks/{id}
DELETE /api/tasks/{id}
```

Example task payload:

```json
{
  "title": "Plan the next release",
  "owner": "Seb",
  "priority": "high",
  "minutes": 30
}
```

`PATCH /api/tasks/{id}` with an empty body toggles the task's done state. Send a JSON body to update specific fields (`title`, `owner`, `priority`, `minutes`, `done`).

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