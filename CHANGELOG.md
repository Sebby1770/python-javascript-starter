# Changelog

All notable changes to TaskPulse are documented in this file.

## [2.0.0] - 2026-07-05

### Added

- Task fields: `due_date` (ISO date), `tags` (string list), and `status` (`todo` | `doing` | `done`).
- Kanban board UI with drag-and-drop columns and status buttons.
- Inline task title editing saved via `PATCH`.
- Export/import endpoints: `GET /api/tasks/export` and `POST /api/tasks/import`.
- WebSocket live sync at `/ws` broadcasting `tasks_changed` events.
- SQLite storage driver via `STORAGE_DRIVER=sqlite` and `store_sqlite.py`.
- `create_store()` factory selecting JSON or SQLite backends.
- OpenAPI specification at `openapi.yaml` served by `GET /api/openapi`.
- Optional `API_KEY` auth for mutating routes using `X-API-Key`.
- Frontend filters for tag and due today.
- GitHub Actions CI workflow for Python and JavaScript tests.
- Dockerfile based on Python 3.12 slim.

### Changed

- Task board layout moved from priority grid to status-based kanban columns.
- Default sample tasks now include tags.
- README and tests expanded for v2 API and UI behavior.

## [2026-07-05]

### Added

- JSON file persistence for tasks at `data/tasks.json` (load on startup, save on changes).
- Task store methods: `toggle_task`, `delete_task`, `update_task`, and `get_stats`.
- API routes: `GET /api/stats`, `PATCH /api/tasks/{id}`, and `DELETE /api/tasks/{id}`.
- Stats dashboard showing total, completed, pending, and minutes by priority.
- Search/filter input for tasks by title, owner, or priority.
- Complete and delete buttons on each task card.
- Dark mode toggle with `localStorage` persistence.
- Frontend helpers: `filterTasks`, `computeStats`, and `formatMinutes`.
- Expanded Python and JavaScript test coverage.

### Changed

- Polished UI with improved typography, animations, and empty states.
- Thread-safe store operations using a `Lock` across reads and writes.