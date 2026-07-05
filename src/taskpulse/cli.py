from __future__ import annotations

import argparse
import json
import sys

from .store import create_store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taskpulse",
        description="TaskPulse command-line interface",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Create a new task")
    add_parser.add_argument("title", help="Task title")
    add_parser.add_argument("--owner", default="Unassigned", help="Task owner")
    add_parser.add_argument(
        "--priority",
        choices=["low", "medium", "high"],
        default="medium",
        help="Task priority",
    )
    add_parser.add_argument("--minutes", type=int, default=25, help="Estimated minutes")
    add_parser.add_argument("--due-date", dest="due_date", help="ISO due date (YYYY-MM-DD)")
    add_parser.add_argument("--tags", help="Comma-separated tags")
    add_parser.add_argument(
        "--status",
        choices=["todo", "doing", "done"],
        default="todo",
        help="Initial status",
    )
    add_parser.add_argument(
        "--blocked-by",
        dest="blocked_by",
        help="Comma-separated blocker task IDs",
    )
    add_parser.add_argument(
        "--recurrence",
        choices=["daily", "weekly", "monthly"],
        help="Recurring schedule",
    )

    subparsers.add_parser("list", help="List all tasks")

    done_parser = subparsers.add_parser("done", help="Mark a task as done")
    done_parser.add_argument("task_id", type=int, help="Task ID")

    subparsers.add_parser("stats", help="Show task statistics")

    return parser


def parse_blocked_by(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def cmd_add(store, args: argparse.Namespace) -> int:
    task = store.add_task(
        title=args.title,
        owner=args.owner,
        priority=args.priority,
        minutes=args.minutes,
        due_date=args.due_date,
        tags=parse_tags(args.tags),
        status=args.status,
        blocked_by=parse_blocked_by(args.blocked_by),
        recurrence=args.recurrence,
    )
    print(json.dumps(task, indent=2))
    return 0


def cmd_list(store, _args: argparse.Namespace) -> int:
    tasks = store.list_tasks()
    if not tasks:
        print("No tasks.")
        return 0

    for task in tasks:
        status = task["status"]
        blocked = task.get("blocked_by") or []
        blocked_label = f" blocked_by={blocked}" if blocked else ""
        recurrence = task.get("recurrence")
        recurrence_label = f" recurrence={recurrence}" if recurrence else ""
        print(
            f"#{task['id']} [{status}] {task['title']} "
            f"({task['priority']}, {task['owner']}, {task['minutes']}m)"
            f"{blocked_label}{recurrence_label}"
        )
    return 0


def cmd_done(store, args: argparse.Namespace) -> int:
    task = store.update_task(args.task_id, {"status": "done", "done": True})
    print(f"Marked #{task['id']} as done: {task['title']}")
    return 0


def cmd_stats(store, _args: argparse.Namespace) -> int:
    stats = store.get_stats()
    print(json.dumps(stats, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = create_store()

    handlers = {
        "add": cmd_add,
        "list": cmd_list,
        "done": cmd_done,
        "stats": cmd_stats,
    }

    try:
        return handlers[args.command](store, args)
    except (KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())