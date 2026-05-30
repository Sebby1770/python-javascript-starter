# TaskPulse

TaskPulse is a small Python and JavaScript starter project. It pairs a standard-library Python API with a vanilla JavaScript frontend so you can run a full-stack app without installing a framework first.

## Features

- Python HTTP API with health checks, task listing, and task creation.
- Browser UI built with HTML, CSS, and modern JavaScript modules.
- Shared task-shaping logic covered by Node's built-in test runner.
- Python unit tests using the standard `unittest` module.

## Project Structure

```text
.
├── src/taskpulse/        Python API and task store
├── tests/                Python tests
├── web/                  JavaScript frontend
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
GET  /api/health
GET  /api/tasks
POST /api/tasks
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
