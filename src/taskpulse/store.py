from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import count
from threading import Lock
from typing import Iterable


VALID_PRIORITIES = {"low", "medium", "high"}


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
    def __init__(self, initial_tasks: Iterable[dict[str, object]] | None = None):
        self._tasks: list[Task] = []
        self._ids = count(1)
        self._lock = Lock()

        for task in initial_tasks or []:
            self.add_task(
                title=str(task.get("title", "")),
                owner=str(task.get("owner", "Unassigned")),
                priority=str(task.get("priority", "medium")),
                minutes=int(task.get("minutes", 25)),
            )

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
            return task.to_dict()


def create_default_store() -> TaskStore:
    return TaskStore(
        [
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
    )
