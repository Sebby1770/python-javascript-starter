# Changelog

All notable changes to TaskPulse are documented in this file.

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