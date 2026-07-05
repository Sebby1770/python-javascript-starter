from __future__ import annotations

import copy
import json
import sqlite3
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from threading import Lock

from .store import (
    ActivityEvent,
    DEFAULT_TASKS,
    MAX_ACTIVITY_EVENTS,
    MAX_UNDO_ACTIONS,
    Task,
    UndoAction,
    VALID_ACTIVITY_EVENTS,
    apply_task_fields,
    is_blocked,
    normalise_blocked_by,
    normalise_tags,
    recurrence_period_elapsed,
    sync_done_and_status,
    validate_due_date,
    validate_recurrence,
    validate_sprint,
    validate_status,
    VALID_PRIORITIES,
)


class SqliteTaskStore:
    def __init__(self, *, db_path: Path):
        self._db_path = db_path
        self._lock = Lock()
        self._ids = count(1)
        self._connection: sqlite3.Connection | None = None
        self._activity: list[ActivityEvent] = []
        self._undo_stack: list[UndoAction] = []
        is_new_db = not db_path.exists()
        self._init_db()
        self._load_ids()
        if is_new_db:
            self._seed_defaults_locked()

    def list_tasks(self) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM tasks ORDER BY id ASC"
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def add_task(
        self,
        *,
        title: str,
        owner: str = "Unassigned",
        priority: str = "medium",
        minutes: int = 25,
        due_date: str | None = None,
        tags: list[str] | None = None,
        status: str = "todo",
        blocked_by: list[int] | None = None,
        recurrence: str | None = None,
        sprint: str | None = None,
    ) -> dict[str, object]:
        title = title.strip()
        owner = owner.strip() or "Unassigned"
        priority = priority.lower().strip()
        due_date = validate_due_date(due_date)
        tags = normalise_tags(tags or [])
        status = validate_status(status)
        blocked_by = normalise_blocked_by(blocked_by or [])
        recurrence = validate_recurrence(recurrence)
        sprint = validate_sprint(sprint)

        if not title:
            raise ValueError("Task title is required.")
        if priority not in VALID_PRIORITIES:
            raise ValueError("Priority must be low, medium, or high.")
        if minutes < 1:
            raise ValueError("Minutes must be at least 1.")

        done, status = sync_done_and_status(done=False, status=status)

        with self._lock:
            tasks_by_id = {
                int(row["id"]): row for row in self._conn().execute("SELECT id FROM tasks")
            }
            for blocker_id in blocked_by:
                if blocker_id not in tasks_by_id:
                    raise ValueError(f"Blocking task {blocker_id} not found.")

            task_id = next(self._ids)
            created_at = datetime.now(timezone.utc).isoformat()
            self._conn().execute(
                """
                INSERT INTO tasks (
                    id, title, owner, priority, minutes, done, status,
                    due_date, tags, blocked_by, recurrence, last_recurred_at,
                    actual_minutes, started_at, sprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    title,
                    owner,
                    priority,
                    minutes,
                    int(done),
                    status,
                    due_date,
                    json.dumps(tags),
                    json.dumps(blocked_by),
                    recurrence,
                    None,
                    0,
                    None,
                    sprint,
                    created_at,
                ),
            )
            self._push_undo_locked("add", {"task_id": task_id})
            self._log_activity_locked(
                "task_created",
                task_id,
                f'Created "{title}"',
            )
            self._conn().commit()
            return {
                "id": task_id,
                "title": title,
                "owner": owner,
                "priority": priority,
                "minutes": minutes,
                "done": done,
                "status": status,
                "due_date": due_date,
                "tags": tags,
                "blocked_by": blocked_by,
                "recurrence": recurrence,
                "last_recurred_at": None,
                "actual_minutes": 0,
                "started_at": None,
                "sprint": sprint,
                "created_at": created_at,
            }

    def toggle_task(self, task_id: int) -> dict[str, object]:
        with self._lock:
            row = self._get_row_locked(task_id)
            previous = self._row_to_dict(row)
            done = not bool(row["done"])
            status = "done" if done else "todo"
            self._push_undo_locked("toggle", {"task_id": task_id, "previous": previous})
            self._conn().execute(
                "UPDATE tasks SET done = ?, status = ? WHERE id = ?",
                (int(done), status, task_id),
            )
            if done:
                self._log_activity_locked(
                    "task_completed",
                    task_id,
                    f'Completed "{row["title"]}"',
                )
            else:
                self._log_activity_locked(
                    "task_updated",
                    task_id,
                    f'Reopened "{row["title"]}"',
                )
            self._conn().commit()
            return self._row_to_dict({**dict(row), "done": int(done), "status": status})

    def delete_task(self, task_id: int) -> dict[str, object]:
        with self._lock:
            row = self._get_row_locked(task_id)
            removed = self._row_to_dict(row)
            self._push_undo_locked("delete", {"task": removed})
            self._log_activity_locked(
                "task_deleted",
                task_id,
                f'Deleted "{row["title"]}"',
            )
            self._conn().execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self._conn().commit()
            return removed

    def update_task(self, task_id: int, fields: dict[str, object]) -> dict[str, object]:
        with self._lock:
            row = self._get_row_locked(task_id)
            task = self._row_to_task(row)
            previous = task.to_dict()
            previous_status = task.status
            tasks_by_id = {
                int(item["id"]): self._row_to_task(item)
                for item in self._conn().execute("SELECT * FROM tasks").fetchall()
            }

            if "blocked_by" in fields:
                blocked_by = normalise_blocked_by(fields["blocked_by"])
                if task_id in blocked_by:
                    raise ValueError("A task cannot block itself.")
                for blocker_id in blocked_by:
                    if blocker_id not in tasks_by_id:
                        raise ValueError(f"Blocking task {blocker_id} not found.")

            if "status" in fields and str(fields["status"]).lower().strip() == "doing":
                if is_blocked(task, tasks_by_id):
                    blockers = [
                        blocker_id
                        for blocker_id in task.blocked_by
                        if blocker_id in tasks_by_id and not tasks_by_id[blocker_id].done
                    ]
                    raise ValueError(
                        f"Task is blocked by incomplete tasks: {', '.join(f'#{item}' for item in blockers)}"
                    )

            apply_task_fields(task, fields)
            self._push_undo_locked(
                "update",
                {"task_id": task_id, "previous": previous},
            )
            self._conn().execute(
                """
                UPDATE tasks
                SET title = ?, owner = ?, priority = ?, minutes = ?, done = ?,
                    status = ?, due_date = ?, tags = ?, blocked_by = ?,
                    recurrence = ?, last_recurred_at = ?,
                    actual_minutes = ?, started_at = ?, sprint = ?
                WHERE id = ?
                """,
                (
                    task.title,
                    task.owner,
                    task.priority,
                    task.minutes,
                    int(task.done),
                    task.status,
                    task.due_date,
                    json.dumps(task.tags),
                    json.dumps(task.blocked_by),
                    task.recurrence,
                    task.last_recurred_at,
                    task.actual_minutes,
                    task.started_at,
                    task.sprint,
                    task_id,
                ),
            )

            if "started_at" in fields or "actual_minutes" in fields:
                if fields.get("started_at") is None and previous.get("started_at"):
                    self._log_activity_locked(
                        "time_tracked",
                        task.id,
                        f'Tracked time on "{task.title}" ({task.actual_minutes} min)',
                    )
            elif "status" in fields and task.status != previous_status:
                if task.status == "done":
                    self._log_activity_locked(
                        "task_completed",
                        task.id,
                        f'Completed "{task.title}"',
                    )
                else:
                    self._log_activity_locked(
                        "task_moved",
                        task.id,
                        f'Moved "{task.title}" to {task.status}',
                    )
            else:
                self._log_activity_locked(
                    "task_updated",
                    task.id,
                    f'Updated "{task.title}"',
                )

            self._conn().commit()
            return task.to_dict()

    def get_stats(self) -> dict[str, object]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT priority, minutes, actual_minutes, done, sprint FROM tasks"
            ).fetchall()
            total = len(rows)
            completed = sum(1 for row in rows if bool(row["done"]))
            minutes_by_priority = {priority: 0 for priority in VALID_PRIORITIES}
            estimated_minutes = 0
            actual_minutes = 0
            by_sprint: dict[str, dict[str, object]] = {}

            for row in rows:
                minutes_by_priority[row["priority"]] += int(row["minutes"])
                estimated_minutes += int(row["minutes"])
                actual = int(row["actual_minutes"] if "actual_minutes" in row.keys() else 0)
                actual_minutes += actual

                sprint_key = row["sprint"] if row["sprint"] else "unassigned"
                if sprint_key not in by_sprint:
                    by_sprint[sprint_key] = {
                        "total": 0,
                        "completed": 0,
                        "pending": 0,
                        "estimated_minutes": 0,
                        "actual_minutes": 0,
                    }
                sprint_stats = by_sprint[sprint_key]
                sprint_stats["total"] = int(sprint_stats["total"]) + 1
                if bool(row["done"]):
                    sprint_stats["completed"] = int(sprint_stats["completed"]) + 1
                else:
                    sprint_stats["pending"] = int(sprint_stats["pending"]) + 1
                sprint_stats["estimated_minutes"] = (
                    int(sprint_stats["estimated_minutes"]) + int(row["minutes"])
                )
                sprint_stats["actual_minutes"] = (
                    int(sprint_stats["actual_minutes"]) + actual
                )

            return {
                "total": total,
                "completed": completed,
                "pending": total - completed,
                "minutes_by_priority": minutes_by_priority,
                "estimated_minutes": estimated_minutes,
                "actual_minutes": actual_minutes,
                "by_sprint": by_sprint,
            }

    def import_tasks(self, tasks: list[dict[str, object]]) -> list[dict[str, object]]:
        if not isinstance(tasks, list):
            raise ValueError("Import payload must be a JSON array of tasks.")

        parsed: list[Task] = []
        max_id = 0
        for item in tasks:
            if not isinstance(item, dict):
                raise ValueError("Each imported task must be a JSON object.")
            task = self._dict_to_task(item)
            parsed.append(task)
            max_id = max(max_id, task.id)

        with self._lock:
            conn = self._conn()
            previous_tasks = [
                self._row_to_dict(row)
                for row in conn.execute("SELECT * FROM tasks ORDER BY id ASC").fetchall()
            ]
            self._push_undo_locked("import", {"tasks": previous_tasks})
            conn.execute("DELETE FROM tasks")
            for task in parsed:
                conn.execute(
                    """
                    INSERT INTO tasks (
                        id, title, owner, priority, minutes, done, status,
                        due_date, tags, blocked_by, recurrence, last_recurred_at,
                        actual_minutes, started_at, sprint, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.id,
                        task.title,
                        task.owner,
                        task.priority,
                        task.minutes,
                        int(task.done),
                        task.status,
                        task.due_date,
                        json.dumps(task.tags),
                        json.dumps(task.blocked_by),
                        task.recurrence,
                        task.last_recurred_at,
                        task.actual_minutes,
                        task.started_at,
                        task.sprint,
                        task.created_at,
                    ),
                )
            self._log_activity_locked(
                "task_imported",
                None,
                f"Imported {len(parsed)} tasks",
            )
            conn.commit()
            self._ids = count(max_id + 1)
            return [task.to_dict() for task in parsed]

    def get_activity(self) -> list[dict[str, object]]:
        with self._lock:
            return [event.to_dict() for event in reversed(self._activity)]

    def undo_last(self) -> dict[str, object]:
        with self._lock:
            if not self._undo_stack:
                raise ValueError("Nothing to undo.")

            action = self._undo_stack.pop()
            conn = self._conn()
            result: dict[str, object]

            if action.action == "add":
                task_id = int(action.payload["task_id"])
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                result = {"undone": "add", "task_id": task_id}

            elif action.action == "delete":
                task_data = copy.deepcopy(action.payload["task"])
                task = self._dict_to_task(task_data)
                conn.execute(
                    """
                    INSERT INTO tasks (
                        id, title, owner, priority, minutes, done, status,
                        due_date, tags, blocked_by, recurrence, last_recurred_at,
                        actual_minutes, started_at, sprint, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.id,
                        task.title,
                        task.owner,
                        task.priority,
                        task.minutes,
                        int(task.done),
                        task.status,
                        task.due_date,
                        json.dumps(task.tags),
                        json.dumps(task.blocked_by),
                        task.recurrence,
                        task.last_recurred_at,
                        task.actual_minutes,
                        task.started_at,
                        task.sprint,
                        task.created_at,
                    ),
                )
                max_id = conn.execute("SELECT MAX(id) AS max_id FROM tasks").fetchone()["max_id"]
                self._ids = count(int(max_id or 0) + 1)
                result = {"undone": "delete", "task": task.to_dict()}

            elif action.action in {"update", "toggle"}:
                task_id = int(action.payload["task_id"])
                previous = copy.deepcopy(action.payload["previous"])
                task = self._dict_to_task({**previous, "id": task_id})
                conn.execute(
                    """
                    UPDATE tasks
                    SET title = ?, owner = ?, priority = ?, minutes = ?, done = ?,
                        status = ?, due_date = ?, tags = ?, blocked_by = ?,
                        recurrence = ?, last_recurred_at = ?,
                        actual_minutes = ?, started_at = ?, sprint = ?
                    WHERE id = ?
                    """,
                    (
                        task.title,
                        task.owner,
                        task.priority,
                        task.minutes,
                        int(task.done),
                        task.status,
                        task.due_date,
                        json.dumps(task.tags),
                        json.dumps(task.blocked_by),
                        task.recurrence,
                        task.last_recurred_at,
                        task.actual_minutes,
                        task.started_at,
                        task.sprint,
                        task_id,
                    ),
                )
                result = {"undone": action.action, "task": task.to_dict()}

            elif action.action == "import":
                previous_tasks = copy.deepcopy(action.payload["tasks"])
                conn.execute("DELETE FROM tasks")
                max_id = 0
                for item in previous_tasks:
                    task = self._dict_to_task(item)
                    max_id = max(max_id, task.id)
                    conn.execute(
                        """
                        INSERT INTO tasks (
                            id, title, owner, priority, minutes, done, status,
                            due_date, tags, blocked_by, recurrence, last_recurred_at,
                            actual_minutes, started_at, sprint, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            task.id,
                            task.title,
                            task.owner,
                            task.priority,
                            task.minutes,
                            int(task.done),
                            task.status,
                            task.due_date,
                            json.dumps(task.tags),
                            json.dumps(task.blocked_by),
                            task.recurrence,
                            task.last_recurred_at,
                            task.actual_minutes,
                            task.started_at,
                            task.sprint,
                            task.created_at,
                        ),
                    )
                self._ids = count(max_id + 1)
                result = {
                    "undone": "import",
                    "tasks": previous_tasks,
                }

            else:
                raise ValueError(f"Unknown undo action: {action.action}")

            self._log_activity_locked("undo", None, f"Undid {action.action}")
            conn.commit()
            return result

    def process_recurring_tasks(self) -> list[dict[str, object]]:
        created: list[dict[str, object]] = []
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            rows = self._conn().execute(
                "SELECT * FROM tasks WHERE recurrence IS NOT NULL"
            ).fetchall()
            conn = self._conn()

            for row in rows:
                source = self._row_to_task(row)
                if not source.recurrence:
                    continue
                if not recurrence_period_elapsed(
                    source.recurrence,
                    last_recurred_at=source.last_recurred_at,
                    created_at=source.created_at,
                ):
                    continue

                clone_id = next(self._ids)
                conn.execute(
                    """
                    INSERT INTO tasks (
                        id, title, owner, priority, minutes, done, status,
                        due_date, tags, blocked_by, recurrence, last_recurred_at,
                        actual_minutes, started_at, sprint, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clone_id,
                        source.title,
                        source.owner,
                        source.priority,
                        source.minutes,
                        0,
                        "todo",
                        source.due_date,
                        json.dumps(source.tags),
                        json.dumps(source.blocked_by),
                        None,
                        None,
                        0,
                        None,
                        source.sprint,
                        now,
                    ),
                )
                conn.execute(
                    "UPDATE tasks SET last_recurred_at = ? WHERE id = ?",
                    (now, source.id),
                )
                created.append(
                    {
                        "id": clone_id,
                        "title": source.title,
                        "owner": source.owner,
                        "priority": source.priority,
                        "minutes": source.minutes,
                        "done": False,
                        "status": "todo",
                        "due_date": source.due_date,
                        "tags": list(source.tags),
                        "blocked_by": list(source.blocked_by),
                        "recurrence": None,
                        "last_recurred_at": None,
                        "created_at": now,
                    }
                )

            if created:
                conn.commit()
        return created

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                owner TEXT NOT NULL,
                priority TEXT NOT NULL,
                minutes INTEGER NOT NULL,
                done INTEGER NOT NULL,
                status TEXT NOT NULL,
                due_date TEXT,
                tags TEXT NOT NULL,
                blocked_by TEXT NOT NULL DEFAULT '[]',
                recurrence TEXT,
                last_recurred_at TEXT,
                actual_minutes INTEGER NOT NULL DEFAULT 0,
                started_at TEXT,
                sprint TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self._migrate_schema(conn)
        conn.commit()

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "blocked_by" not in columns:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN blocked_by TEXT NOT NULL DEFAULT '[]'"
            )
        if "recurrence" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN recurrence TEXT")
        if "last_recurred_at" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN last_recurred_at TEXT")
        if "actual_minutes" not in columns:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN actual_minutes INTEGER NOT NULL DEFAULT 0"
            )
        if "started_at" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN started_at TEXT")
        if "sprint" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN sprint TEXT")

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def _load_ids(self) -> None:
        with self._lock:
            row = self._conn().execute("SELECT MAX(id) AS max_id FROM tasks").fetchone()
            max_id = int(row["max_id"] or 0)
            self._ids = count(max_id + 1)

    def _seed_defaults_locked(self) -> None:
        conn = self._conn()
        for task in DEFAULT_TASKS:
            task_id = next(self._ids)
            created_at = datetime.now(timezone.utc).isoformat()
            tags = normalise_tags(task.get("tags", []))
            conn.execute(
                """
                INSERT INTO tasks (
                    id, title, owner, priority, minutes, done, status,
                    due_date, tags, blocked_by, recurrence, last_recurred_at,
                    actual_minutes, started_at, sprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    str(task["title"]),
                    str(task["owner"]),
                    str(task["priority"]),
                    int(task["minutes"]),
                    0,
                    "todo",
                    None,
                    json.dumps(tags),
                    "[]",
                    None,
                    None,
                    0,
                    None,
                    None,
                    created_at,
                ),
            )
        conn.commit()

    def _get_row_locked(self, task_id: int) -> sqlite3.Row:
        row = self._conn().execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Task {task_id} not found.")
        return row

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, object]:
        return self._row_to_task(row).to_dict()

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        done = bool(row["done"])
        status = str(row["status"])
        done, status = sync_done_and_status(done=done, status=status)
        blocked_raw = row["blocked_by"] if "blocked_by" in row.keys() else "[]"
        return Task(
            id=int(row["id"]),
            title=str(row["title"]),
            owner=str(row["owner"]),
            priority=str(row["priority"]),
            minutes=int(row["minutes"]),
            done=done,
            status=status,
            due_date=validate_due_date(row["due_date"]),
            tags=normalise_tags(json.loads(row["tags"] or "[]")),
            blocked_by=normalise_blocked_by(json.loads(blocked_raw or "[]")),
            recurrence=validate_recurrence(row["recurrence"] if "recurrence" in row.keys() else None),
            last_recurred_at=(
                str(row["last_recurred_at"])
                if "last_recurred_at" in row.keys() and row["last_recurred_at"]
                else None
            ),
            actual_minutes=max(
                0,
                int(row["actual_minutes"] if "actual_minutes" in row.keys() else 0),
            ),
            started_at=(
                str(row["started_at"])
                if "started_at" in row.keys() and row["started_at"]
                else None
            ),
            sprint=validate_sprint(row["sprint"] if "sprint" in row.keys() else None),
            created_at=str(row["created_at"]),
        )

    def _dict_to_task(self, task: dict[str, object]) -> Task:
        done = bool(task.get("done", False))
        status = str(task.get("status", "done" if done else "todo")).lower().strip()
        done, status = sync_done_and_status(done=done, status=status)
        return Task(
            id=int(task.get("id", 0)),
            title=str(task.get("title", "")),
            owner=str(task.get("owner", "Unassigned")),
            priority=str(task.get("priority", "medium")),
            minutes=int(task.get("minutes", 25)),
            done=done,
            status=status,
            due_date=validate_due_date(task.get("due_date")),
            tags=normalise_tags(task.get("tags", [])),
            blocked_by=normalise_blocked_by(task.get("blocked_by", [])),
            recurrence=validate_recurrence(task.get("recurrence")),
            last_recurred_at=(
                str(task["last_recurred_at"])
                if task.get("last_recurred_at")
                else None
            ),
            actual_minutes=max(0, int(task.get("actual_minutes", 0))),
            started_at=(
                str(task["started_at"]) if task.get("started_at") else None
            ),
            sprint=validate_sprint(task.get("sprint")),
            created_at=str(
                task.get("created_at", datetime.now(timezone.utc).isoformat())
            ),
        )

    def _log_activity_locked(
        self,
        event: str,
        task_id: int | None,
        message: str,
    ) -> None:
        if event not in VALID_ACTIVITY_EVENTS:
            raise ValueError(f"Unknown activity event: {event}")
        self._activity.append(
            ActivityEvent(event=event, task_id=task_id, message=message)
        )
        if len(self._activity) > MAX_ACTIVITY_EVENTS:
            self._activity = self._activity[-MAX_ACTIVITY_EVENTS:]

    def _push_undo_locked(self, action: str, payload: dict[str, object]) -> None:
        self._undo_stack.append(UndoAction(action=action, payload=payload))
        if len(self._undo_stack) > MAX_UNDO_ACTIONS:
            self._undo_stack = self._undo_stack[-MAX_UNDO_ACTIONS:]