# Changelog

All notable changes to TaskPulse are documented in this file.

## [4.0.0] - 2026-07-05

### Added

- Time tracking with `actual_minutes` and `started_at` on tasks; start/stop timer on cards (separate from Pomodoro).
- Activity feed storing the last 50 events (`task_created`, `task_completed`, `task_moved`, etc.) with `GET /api/activity`.
- Task templates: built-in Bug fix, Feature, Meeting, and Review presets plus custom templates in `localStorage`.
- Keyboard shortcuts: `n` new task, `/` search, `1/2/3` kanban column filter, `?` shortcuts modal, `f` focus mode, `Esc` close overlays.
- Weekly review sidebar panel for overdue, stale doing (>3 days), and untagged high-priority tasks.
- Undo stack for the last 10 mutating actions with `POST /api/undo` and header undo button.
- Sprint field (`sprint`) with sprint filter dropdown and per-sprint stats.
- Stats dashboard now shows estimated vs actual minute totals.

### Changed

- Task model, JSON/SQLite stores, OpenAPI spec, frontend UI, tests, and README updated for v4 fields and routes.

## [3.0.0] - 2026-07-05

### Added

- Natural language task input via `nlp.py` and `POST /api/tasks/parse`.
- Quick add mode in the UI with live parse preview before submit.
- Pomodoro timer on task cards with countdown overlay, notifications, and optional tick sound.
- Focus mode fullscreen overlay cycling high-priority pending tasks.
- Task dependencies with `blocked_by: list[int]`; blocked tasks cannot move to `doing`.
- Burndown chart tracking daily pending counts in `localStorage`.
- CLI tool: `python -m taskpulse.cli` with `add`, `list`, `done`, and `stats` commands.
- WebSocket presence system with random clerk names and header pill.
- Recurring tasks stub with `recurrence` field (`daily`, `weekly`, `monthly`) and auto-clone on server start.
- Tests for NLP parsing, dependencies, recurrence, and frontend helpers.

### Changed

- Task model, JSON/SQLite stores, OpenAPI spec, and README updated for v3 fields and routes.
- WebSocket hub now broadcasts `presence_changed` events alongside `tasks_changed`.

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