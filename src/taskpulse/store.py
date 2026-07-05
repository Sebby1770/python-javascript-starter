from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from threading import Lock
from typing import Iterable


VALID_PRIORITIES = {"low", "medium", "high"}

DEFAULT_TASKS: list[dict[str, object]] = [
    {
        "title": "Connect the Python API",
        "owner": "Seb",
        "priority": "high",
        "minutes": 35,
    },
    {
        "title": "Polish the JavaScript UI",
        "owner": "Frontend",
        "priority": "medium",
        "minutes": 25,
    },
    {
        "title": "Ship the first GitHub commit",
        "owner": "Codex",
        "priority": "low",
        "minutes": 15,
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
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


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
    ) -> dict[str, object]:
        title = title.strip()
        owner = owner.strip() or "Unassigned"
        priority = priority.lower().strip()

        if not title:
            raise ValueError("Task title is required.")
        if priority not in VALID_PRIORITIES:
            raise ValueError("Priority must be low, medium, or high.")
        if minutes < 1:
            raise ValueError("Minutes must be at least 1.")

        with self._lock:
            task = Task(
                id=next(self._ids),
                title=title,
                owner=owner,
                priority=priority,
                minutes=minutes,
            )
            self._tasks.append(task)
            self._save_locked()
            return task.to_dict()

    def toggle_task(self, task_id: int) -> dict[str, object]:
        with self._lock:
            task = self._get_task_locked(task_id)
            task.done = not task.done
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

            if "done" in fields:
                task.done = bool(fields["done"])

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

    def _task_from_dict(self, task: dict[str, object]) -> Task:
        return Task(
            id=int(task.get("id", next(self._ids))),
            title=str(task.get("title", "")),
            owner=str(task.get("owner", "Unassigned")),
            priority=str(task.get("priority", "medium")),
            minutes=int(task.get("minutes", 25)),
            done=bool(task.get("done", False)),
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


def default_data_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "tasks.json"


def create_default_store(data_path: Path | None = None) -> TaskStore:
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
            )

    return store