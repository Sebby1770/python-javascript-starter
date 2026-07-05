from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from threading import Lock

from .store import (
    DEFAULT_TASKS,
    Task,
    apply_task_fields,
    is_blocked,
    normalise_blocked_by,
    normalise_tags,
    recurrence_period_elapsed,
    sync_done_and_status,
    validate_due_date,
    validate_recurrence,
    validate_status,
    VALID_PRIORITIES,
)


class SqliteTaskStore:
    def __init__(self, *, db_path: Path):
        self._db_path = db_path
        self._lock = Lock()
        self._ids = count(1)
        self._connection: sqlite3.Connection | None = None
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
    ) -> dict[str, object]:
        title = title.strip()
        owner = owner.strip() or "Unassigned"
        priority = priority.lower().strip()
        due_date = validate_due_date(due_date)
        tags = normalise_tags(tags or [])
        status = validate_status(status)
        blocked_by = normalise_blocked_by(blocked_by or [])
        recurrence = validate_recurrence(recurrence)

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
                    due_date, tags, blocked_by, recurrence, last_recurred_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    created_at,
                ),
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
                "created_at": created_at,
            }

    def toggle_task(self, task_id: int) -> dict[str, object]:
        with self._lock:
            row = self._get_row_locked(task_id)
            done = not bool(row["done"])
            status = "done" if done else "todo"
            self._conn().execute(
                "UPDATE tasks SET done = ?, status = ? WHERE id = ?",
                (int(done), status, task_id),
            )
            self._conn().commit()
            return self._row_to_dict({**dict(row), "done": int(done), "status": status})

    def delete_task(self, task_id: int) -> dict[str, object]:
        with self._lock:
            row = self._get_row_locked(task_id)
            removed = self._row_to_dict(row)
            self._conn().execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self._conn().commit()
            return removed

    def update_task(self, task_id: int, fields: dict[str, object]) -> dict[str, object]:
        with self._lock:
            row = self._get_row_locked(task_id)
            task = self._row_to_task(row)
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
            self._conn().execute(
                """
                UPDATE tasks
                SET title = ?, owner = ?, priority = ?, minutes = ?, done = ?,
                    status = ?, due_date = ?, tags = ?, blocked_by = ?,
                    recurrence = ?, last_recurred_at = ?
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
                    task_id,
                ),
            )
            self._conn().commit()
            return task.to_dict()

    def get_stats(self) -> dict[str, object]:
        with self._lock:
            rows = self._conn().execute("SELECT priority, minutes, done FROM tasks").fetchall()
            total = len(rows)
            completed = sum(1 for row in rows if bool(row["done"]))
            minutes_by_priority = {priority: 0 for priority in VALID_PRIORITIES}
            for row in rows:
                minutes_by_priority[row["priority"]] += int(row["minutes"])
            return {
                "total": total,
                "completed": completed,
                "pending": total - completed,
                "minutes_by_priority": minutes_by_priority,
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
            conn.execute("DELETE FROM tasks")
            for task in parsed:
                conn.execute(
                    """
                    INSERT INTO tasks (
                        id, title, owner, priority, minutes, done, status,
                        due_date, tags, blocked_by, recurrence, last_recurred_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        task.created_at,
                    ),
                )
            conn.commit()
            self._ids = count(max_id + 1)
            return [task.to_dict() for task in parsed]

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
                        due_date, tags, blocked_by, recurrence, last_recurred_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    due_date, tags, blocked_by, recurrence, last_recurred_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            created_at=str(
                task.get("created_at", datetime.now(timezone.utc).isoformat())
            ),
        )