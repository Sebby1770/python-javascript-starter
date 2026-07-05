from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from itertools import count
from pathlib import Path
from threading import Lock
from typing import Iterable, Protocol


VALID_PRIORITIES = {"low", "medium", "high"}
VALID_STATUSES = {"todo", "doing", "done"}
VALID_RECURRENCES = {"daily", "weekly", "monthly"}
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DEFAULT_TASKS: list[dict[str, object]] = [
    {
        "title": "Connect the Python API",
        "owner": "Seb",
        "priority": "high",
        "minutes": 35,
        "tags": ["api", "backend"],
    },
    {
        "title": "Polish the JavaScript UI",
        "owner": "Frontend",
        "priority": "medium",
        "minutes": 25,
        "tags": ["frontend"],
    },
    {
        "title": "Ship the first GitHub commit",
        "owner": "Codex",
        "priority": "low",
        "minutes": 15,
        "tags": ["release"],
    },
]


@dataclass(slots=True)
class Task:
    id: int
    title: str
    owner: str = "Unassigned"
    priority: str = "medium"
    minutes: int = 25
    done: bool = False
    status: str = "todo"
    due_date: str | None = None
    tags: list[str] = field(default_factory=list)
    blocked_by: list[int] = field(default_factory=list)
    recurrence: str | None = None
    last_recurred_at: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TaskStoreProtocol(Protocol):
    def list_tasks(self) -> list[dict[str, object]]: ...

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
    ) -> dict[str, object]: ...

    def toggle_task(self, task_id: int) -> dict[str, object]: ...

    def delete_task(self, task_id: int) -> dict[str, object]: ...

    def update_task(self, task_id: int, fields: dict[str, object]) -> dict[str, object]: ...

    def get_stats(self) -> dict[str, object]: ...

    def import_tasks(self, tasks: list[dict[str, object]]) -> list[dict[str, object]]: ...


def validate_due_date(value: object) -> str | None:
    if value is None or value == "":
        return None
    due_date = str(value).strip()
    if not ISO_DATE_RE.match(due_date):
        raise ValueError("Due date must be an ISO date string (YYYY-MM-DD).")
    try:
        date.fromisoformat(due_date)
    except ValueError as exc:
        raise ValueError("Due date must be an ISO date string (YYYY-MM-DD).") from exc
    return due_date


def normalise_tags(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, list):
        parts = [str(item) for item in value]
    else:
        raise ValueError("Tags must be a list or comma-separated string.")

    tags: list[str] = []
    seen: set[str] = set()
    for part in parts:
        tag = part.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def validate_status(value: object, *, done: bool | None = None) -> str:
    status = str(value).lower().strip()
    if status not in VALID_STATUSES:
        raise ValueError("Status must be todo, doing, or done.")
    if done is True:
        return "done"
    if done is False and status == "done":
        return "todo"
    return status


def sync_done_and_status(*, done: bool, status: str) -> tuple[bool, str]:
    if status == "done":
        return True, "done"
    if done:
        return True, "done"
    if status not in VALID_STATUSES:
        status = "todo"
    return done, status


def validate_recurrence(value: object) -> str | None:
    if value is None or value == "":
        return None
    recurrence = str(value).lower().strip()
    if recurrence not in VALID_RECURRENCES:
        raise ValueError("Recurrence must be daily, weekly, or monthly.")
    return recurrence


def normalise_blocked_by(value: object) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("blocked_by must be a list of task IDs.")
    blocked: list[int] = []
    seen: set[int] = set()
    for item in value:
        task_id = int(item)
        if task_id <= 0 or task_id in seen:
            continue
        seen.add(task_id)
        blocked.append(task_id)
    return blocked


def apply_task_fields(task: Task, fields: dict[str, object]) -> None:
    if "title" in fields:
        title = str(fields["title"]).strip()
        if not title:
            raise ValueError("Task title is required.")
        task.title = title

    if "owner" in fields:
        task.owner = str(fields["owner"]).strip() or "Unassigned"

    if "priority" in fields:
        priority = str(fields["priority"]).lower().strip()
        if priority not in VALID_PRIORITIES:
            raise ValueError("Priority must be low, medium, or high.")
        task.priority = priority

    if "minutes" in fields:
        minutes = int(fields["minutes"])
        if minutes < 1:
            raise ValueError("Minutes must be at least 1.")
        task.minutes = minutes

    if "due_date" in fields:
        task.due_date = validate_due_date(fields["due_date"])

    if "tags" in fields:
        task.tags = normalise_tags(fields["tags"])

    if "blocked_by" in fields:
        task.blocked_by = normalise_blocked_by(fields["blocked_by"])

    if "recurrence" in fields:
        task.recurrence = validate_recurrence(fields["recurrence"])

    status_updated = False
    if "status" in fields:
        task.status = validate_status(fields["status"])
        status_updated = True

    if "done" in fields:
        task.done = bool(fields["done"])

    if status_updated and task.status == "done":
        task.done = True
    elif "done" in fields:
        if task.done:
            task.status = "done"
        elif task.status == "done":
            task.status = "todo"

    task.done, task.status = sync_done_and_status(done=task.done, status=task.status)


def is_blocked(task: Task, tasks_by_id: dict[int, Task]) -> bool:
    for blocker_id in task.blocked_by:
        blocker = tasks_by_id.get(blocker_id)
        if blocker is None:
            continue
        if not blocker.done:
            return True
    return False


def recurrence_period_elapsed(
    recurrence: str,
    *,
    last_recurred_at: str | None,
    created_at: str,
    reference: datetime | None = None,
) -> bool:
    now = reference or datetime.now(timezone.utc)
    anchor_raw = last_recurred_at or created_at
    anchor = datetime.fromisoformat(anchor_raw.replace("Z", "+00:00"))
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)

    if recurrence == "daily":
        return anchor.date() < now.date()
    if recurrence == "weekly":
        return (now - anchor).days >= 7
    if recurrence == "monthly":
        return (now.year, now.month) > (anchor.year, anchor.month)
    return False


class TaskStore:
    def __init__(
        self,
        initial_tasks: Iterable[dict[str, object]] | None = None,
        *,
        data_path: Path | None = None,
    ):
        self._tasks: list[Task] = []
        self._ids = count(1)
        self._lock = Lock()
        self._data_path = data_path

        for task in initial_tasks or []:
            self._append_task_from_dict(task)

    def list_tasks(self) -> list[dict[str, object]]:
        with self._lock:
            return [task.to_dict() for task in self._tasks]

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
            tasks_by_id = {task.id: task for task in self._tasks}
            for blocker_id in blocked_by:
                if blocker_id not in tasks_by_id:
                    raise ValueError(f"Blocking task {blocker_id} not found.")

            task = Task(
                id=next(self._ids),
                title=title,
                owner=owner,
                priority=priority,
                minutes=minutes,
                done=done,
                status=status,
                due_date=due_date,
                tags=tags,
                blocked_by=blocked_by,
                recurrence=recurrence,
            )
            self._tasks.append(task)
            self._save_locked()
            return task.to_dict()

    def toggle_task(self, task_id: int) -> dict[str, object]:
        with self._lock:
            task = self._get_task_locked(task_id)
            task.done = not task.done
            task.status = "done" if task.done else "todo"
            self._save_locked()
            return task.to_dict()

    def delete_task(self, task_id: int) -> dict[str, object]:
        with self._lock:
            task = self._get_task_locked(task_id)
            removed = task.to_dict()
            self._tasks = [item for item in self._tasks if item.id != task_id]
            self._save_locked()
            return removed

    def update_task(self, task_id: int, fields: dict[str, object]) -> dict[str, object]:
        with self._lock:
            task = self._get_task_locked(task_id)
            tasks_by_id = {item.id: item for item in self._tasks}

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
            self._save_locked()
            return task.to_dict()

    def get_stats(self) -> dict[str, object]:
        with self._lock:
            total = len(self._tasks)
            completed = sum(1 for task in self._tasks if task.done)
            minutes_by_priority = {priority: 0 for priority in VALID_PRIORITIES}

            for task in self._tasks:
                minutes_by_priority[task.priority] += task.minutes

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
            task = self._task_from_dict(item, assign_id=False)
            parsed.append(task)
            max_id = max(max_id, task.id)

        with self._lock:
            self._tasks = parsed
            self._ids = count(max_id + 1)
            self._save_locked()
            return [task.to_dict() for task in self._tasks]

    def load_from_file(self, path: Path) -> None:
        with self._lock:
            if not path.exists():
                return

            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("Task data must be a JSON array.")

            self._tasks = []
            max_id = 0
            for item in raw:
                if not isinstance(item, dict):
                    continue
                task = self._task_from_dict(item)
                self._tasks.append(task)
                max_id = max(max_id, task.id)

            self._ids = count(max_id + 1)

    def save_to_file(self, path: Path) -> None:
        with self._lock:
            self._save_to_path_locked(path)

    def _append_task_from_dict(self, task: dict[str, object]) -> None:
        with self._lock:
            self._tasks.append(self._task_from_dict(task))
            self._ids = count(max((item.id for item in self._tasks), default=0) + 1)

    def _task_from_dict(
        self,
        task: dict[str, object],
        *,
        assign_id: bool = True,
    ) -> Task:
        done = bool(task.get("done", False))
        status = str(task.get("status", "done" if done else "todo")).lower().strip()
        if status not in VALID_STATUSES:
            status = "done" if done else "todo"
        done, status = sync_done_and_status(done=done, status=status)

        return Task(
            id=int(task.get("id", next(self._ids) if assign_id else 0)),
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
                task.get(
                    "created_at",
                    datetime.now(timezone.utc).isoformat(),
                )
            ),
        )

    def _get_task_locked(self, task_id: int) -> Task:
        for task in self._tasks:
            if task.id == task_id:
                return task
        raise KeyError(f"Task {task_id} not found.")

    def _save_locked(self) -> None:
        if self._data_path is not None:
            self._save_to_path_locked(self._data_path)

    def _save_to_path_locked(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [task.to_dict() for task in self._tasks]
        path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def process_recurring_tasks(self) -> list[dict[str, object]]:
        created: list[dict[str, object]] = []
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            for source in list(self._tasks):
                if not source.recurrence:
                    continue
                if not recurrence_period_elapsed(
                    source.recurrence,
                    last_recurred_at=source.last_recurred_at,
                    created_at=source.created_at,
                ):
                    continue

                clone = Task(
                    id=next(self._ids),
                    title=source.title,
                    owner=source.owner,
                    priority=source.priority,
                    minutes=source.minutes,
                    done=False,
                    status="todo",
                    due_date=source.due_date,
                    tags=list(source.tags),
                    blocked_by=list(source.blocked_by),
                    recurrence=None,
                    created_at=now,
                )
                self._tasks.append(clone)
                source.last_recurred_at = now
                created.append(clone.to_dict())

            if created:
                self._save_locked()
        return created


def default_data_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "tasks.json"


def default_sqlite_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "tasks.db"


def create_store(
    *,
    driver: str | None = None,
    data_path: Path | None = None,
) -> TaskStoreProtocol:
    selected = (driver or os.environ.get("STORAGE_DRIVER", "json")).lower().strip()

    if selected == "sqlite":
        from .store_sqlite import SqliteTaskStore

        return SqliteTaskStore(db_path=data_path or default_sqlite_path())

    path = data_path or default_data_path()
    store = TaskStore(data_path=path)

    if path.exists():
        store.load_from_file(path)
    else:
        for task in DEFAULT_TASKS:
            store.add_task(
                title=str(task["title"]),
                owner=str(task["owner"]),
                priority=str(task["priority"]),
                minutes=int(task["minutes"]),
                tags=list(task.get("tags", [])),
            )

    if hasattr(store, "process_recurring_tasks"):
        store.process_recurring_tasks()

    return store


def create_default_store(data_path: Path | None = None) -> TaskStoreProtocol:
    return create_store(data_path=data_path)