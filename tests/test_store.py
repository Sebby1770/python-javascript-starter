import json
import tempfile
import unittest
from pathlib import Path

from taskpulse.store import (
    TaskStore,
    create_default_store,
    create_store,
    normalise_blocked_by,
    normalise_tags,
    recurrence_period_elapsed,
    validate_due_date,
    validate_recurrence,
)
from taskpulse.store_sqlite import SqliteTaskStore


class TaskStoreTest(unittest.TestCase):
    def test_add_task_trims_title_and_sets_defaults(self):
        store = TaskStore()

        task = store.add_task(title="  Draft README  ")

        self.assertEqual(task["id"], 1)
        self.assertEqual(task["title"], "Draft README")
        self.assertEqual(task["owner"], "Unassigned")
        self.assertEqual(task["priority"], "medium")
        self.assertFalse(task["done"])
        self.assertEqual(task["status"], "todo")
        self.assertIsNone(task["due_date"])
        self.assertEqual(task["tags"], [])

    def test_rejects_blank_titles(self):
        store = TaskStore()

        with self.assertRaisesRegex(ValueError, "title"):
            store.add_task(title=" ")

    def test_rejects_invalid_priority(self):
        store = TaskStore()

        with self.assertRaisesRegex(ValueError, "Priority"):
            store.add_task(title="Ship", priority="urgent")

    def test_rejects_invalid_due_date(self):
        store = TaskStore()

        with self.assertRaisesRegex(ValueError, "Due date"):
            store.add_task(title="Ship", due_date="05-07-2026")

    def test_accepts_tags_and_due_date(self):
        store = TaskStore()

        task = store.add_task(
            title="Tagged",
            due_date="2026-07-05",
            tags=["API", "api", "frontend"],
        )

        self.assertEqual(task["due_date"], "2026-07-05")
        self.assertEqual(task["tags"], ["api", "frontend"])

    def test_lists_tasks_in_creation_order(self):
        store = TaskStore()
        store.add_task(title="First")
        store.add_task(title="Second", priority="high")

        self.assertEqual(
            [task["title"] for task in store.list_tasks()],
            ["First", "Second"],
        )

    def test_toggle_task_flips_done_state_and_status(self):
        store = TaskStore()
        created = store.add_task(title="Toggle me")

        toggled = store.toggle_task(created["id"])
        self.assertTrue(toggled["done"])
        self.assertEqual(toggled["status"], "done")

        toggled_again = store.toggle_task(created["id"])
        self.assertFalse(toggled_again["done"])
        self.assertEqual(toggled_again["status"], "todo")

    def test_delete_task_removes_entry(self):
        store = TaskStore()
        first = store.add_task(title="Keep")
        second = store.add_task(title="Remove")

        removed = store.delete_task(second["id"])

        self.assertEqual(removed["title"], "Remove")
        self.assertEqual([task["id"] for task in store.list_tasks()], [first["id"]])

    def test_delete_missing_task_raises_key_error(self):
        store = TaskStore()

        with self.assertRaises(KeyError):
            store.delete_task(404)

    def test_update_task_changes_fields(self):
        store = TaskStore()
        created = store.add_task(title="Original", owner="Seb", priority="low", minutes=10)

        updated = store.update_task(
            created["id"],
            {
                "title": "Updated",
                "owner": "Team",
                "priority": "high",
                "minutes": 45,
                "done": True,
                "status": "done",
                "due_date": "2026-08-01",
                "tags": "release, docs",
            },
        )

        self.assertEqual(updated["title"], "Updated")
        self.assertEqual(updated["owner"], "Team")
        self.assertEqual(updated["priority"], "high")
        self.assertEqual(updated["minutes"], 45)
        self.assertTrue(updated["done"])
        self.assertEqual(updated["status"], "done")
        self.assertEqual(updated["due_date"], "2026-08-01")
        self.assertEqual(updated["tags"], ["release", "docs"])

    def test_update_task_status_sets_done(self):
        store = TaskStore()
        created = store.add_task(title="Move me", status="doing")

        updated = store.update_task(created["id"], {"status": "done"})
        self.assertTrue(updated["done"])
        self.assertEqual(updated["status"], "done")

    def test_update_task_rejects_invalid_values(self):
        store = TaskStore()
        created = store.add_task(title="Valid")

        with self.assertRaisesRegex(ValueError, "title"):
            store.update_task(created["id"], {"title": "   "})

        with self.assertRaisesRegex(ValueError, "Priority"):
            store.update_task(created["id"], {"priority": "urgent"})

        with self.assertRaisesRegex(ValueError, "Minutes"):
            store.update_task(created["id"], {"minutes": 0})

        with self.assertRaisesRegex(ValueError, "Status"):
            store.update_task(created["id"], {"status": "blocked"})

    def test_get_stats_aggregates_counts_and_minutes(self):
        store = TaskStore()
        store.add_task(title="High", priority="high", minutes=30)
        store.add_task(title="Medium", priority="medium", minutes=20)
        store.add_task(title="Low", priority="low", minutes=10)
        store.toggle_task(1)

        stats = store.get_stats()

        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["pending"], 2)
        self.assertEqual(
            stats["minutes_by_priority"],
            {"high": 30, "medium": 20, "low": 10},
        )
        self.assertEqual(stats["estimated_minutes"], 60)
        self.assertEqual(stats["actual_minutes"], 0)

    def test_add_task_with_sprint_and_time_tracking_fields(self):
        store = TaskStore()
        task = store.add_task(title="Sprint task", sprint="Sprint 12")

        self.assertEqual(task["sprint"], "Sprint 12")
        self.assertEqual(task["actual_minutes"], 0)
        self.assertIsNone(task["started_at"])

    def test_update_task_records_time_tracking(self):
        store = TaskStore()
        created = store.add_task(title="Timed")

        started = store.update_task(
            created["id"],
            {"started_at": "2026-07-05T10:00:00+00:00"},
        )
        self.assertEqual(started["started_at"], "2026-07-05T10:00:00+00:00")

        stopped = store.update_task(
            created["id"],
            {"actual_minutes": 15, "started_at": None},
        )
        self.assertEqual(stopped["actual_minutes"], 15)
        self.assertIsNone(stopped["started_at"])

    def test_get_stats_includes_sprint_breakdown(self):
        store = TaskStore()
        first = store.add_task(title="A", sprint="Sprint 1", minutes=10)
        store.update_task(first["id"], {"actual_minutes": 5})
        store.add_task(title="B", sprint="Sprint 1", minutes=20)
        store.add_task(title="C", minutes=15)

        stats = store.get_stats()

        self.assertEqual(stats["by_sprint"]["Sprint 1"]["total"], 2)
        self.assertEqual(stats["by_sprint"]["Sprint 1"]["estimated_minutes"], 30)
        self.assertEqual(stats["by_sprint"]["Sprint 1"]["actual_minutes"], 5)
        self.assertEqual(stats["by_sprint"]["unassigned"]["total"], 1)

    def test_activity_log_records_events(self):
        store = TaskStore()
        created = store.add_task(title="Feed me")
        store.update_task(created["id"], {"status": "doing"})
        store.delete_task(created["id"])

        activity = store.get_activity()
        events = [item["event"] for item in activity]

        self.assertEqual(events[0], "task_deleted")
        self.assertIn("task_created", events)
        self.assertIn("task_moved", events)
        self.assertLessEqual(len(activity), 50)

    def test_undo_reverts_last_action(self):
        store = TaskStore()
        created = store.add_task(title="Undo me", priority="high")
        store.update_task(created["id"], {"title": "Changed"})

        result = store.undo_last()

        self.assertEqual(result["undone"], "update")
        self.assertEqual(store.list_tasks()[0]["title"], "Undo me")

    def test_undo_reverts_add_and_delete(self):
        store = TaskStore()
        store.add_task(title="Temporary")
        store.undo_last()
        self.assertEqual(store.list_tasks(), [])

        kept = store.add_task(title="Keep")
        deleted = store.delete_task(kept["id"])
        self.assertEqual(deleted["title"], "Keep")
        store.undo_last()
        self.assertEqual(store.list_tasks()[0]["title"], "Keep")

    def test_import_tasks_replaces_existing_tasks(self):
        store = TaskStore()
        store.add_task(title="Old")

        imported = store.import_tasks(
            [
                {
                    "id": 10,
                    "title": "Imported",
                    "owner": "Seb",
                    "priority": "high",
                    "minutes": 15,
                    "done": False,
                    "status": "doing",
                    "due_date": "2026-07-10",
                    "tags": ["api"],
                }
            ]
        )

        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]["title"], "Imported")
        self.assertEqual(imported[0]["status"], "doing")
        self.assertEqual([task["title"] for task in store.list_tasks()], ["Imported"])

        created = store.add_task(title="Next")
        self.assertEqual(created["id"], 11)

    def test_persists_tasks_to_json_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "tasks.json"
            store = TaskStore(data_path=data_path)
            store.add_task(
                title="Persisted",
                owner="Seb",
                priority="high",
                minutes=40,
                due_date="2026-07-05",
                tags=["api"],
            )

            reloaded = TaskStore(data_path=data_path)
            reloaded.load_from_file(data_path)
            tasks = reloaded.list_tasks()

            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["title"], "Persisted")
            self.assertEqual(tasks[0]["due_date"], "2026-07-05")
            self.assertEqual(tasks[0]["tags"], ["api"])

            saved = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual(saved[0]["title"], "Persisted")

    def test_create_default_store_seeds_data_when_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "tasks.json"
            store = create_default_store(data_path)

            tasks = store.list_tasks()
            self.assertEqual(len(tasks), 3)
            self.assertTrue(data_path.exists())

    def test_create_store_uses_sqlite_driver(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "tasks.db"
            store = create_store(driver="sqlite", data_path=db_path)

            self.assertIsInstance(store, SqliteTaskStore)
            self.assertEqual(len(store.list_tasks()), 3)

    def test_add_task_with_blocked_by_and_recurrence(self):
        store = TaskStore()
        blocker = store.add_task(title="Blocker")
        task = store.add_task(
            title="Dependent",
            blocked_by=[blocker["id"]],
            recurrence="weekly",
        )

        self.assertEqual(task["blocked_by"], [blocker["id"]])
        self.assertEqual(task["recurrence"], "weekly")

    def test_cannot_move_blocked_task_to_doing(self):
        store = TaskStore()
        blocker = store.add_task(title="Blocker")
        dependent = store.add_task(title="Dependent", blocked_by=[blocker["id"]])

        with self.assertRaisesRegex(ValueError, "blocked"):
            store.update_task(dependent["id"], {"status": "doing"})

        store.update_task(blocker["id"], {"status": "done", "done": True})
        updated = store.update_task(dependent["id"], {"status": "doing"})
        self.assertEqual(updated["status"], "doing")

    def test_process_recurring_tasks_clones_daily_task(self):
        store = TaskStore()
        store.import_tasks(
            [
                {
                    "id": 1,
                    "title": "Standup",
                    "recurrence": "daily",
                    "created_at": "2026-07-04T10:00:00+00:00",
                }
            ]
        )
        created = store.process_recurring_tasks()

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["title"], "Standup")
        self.assertIsNone(created[0]["recurrence"])
        self.assertEqual(len(store.list_tasks()), 2)
        self.assertIsNotNone(store.list_tasks()[0]["last_recurred_at"])

    def test_sqlite_store_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "tasks.db"
            store = SqliteTaskStore(db_path=db_path)
            store.import_tasks([])
            created = store.add_task(
                title="SQLite task",
                tags=["db"],
                status="doing",
                due_date="2026-07-06",
            )

            reloaded = SqliteTaskStore(db_path=db_path)
            tasks = reloaded.list_tasks()

            self.assertEqual(tasks[0]["title"], created["title"])
            self.assertEqual(tasks[0]["tags"], ["db"])
            self.assertEqual(tasks[0]["status"], "doing")


class ValidationHelpersTest(unittest.TestCase):
    def test_validate_due_date_accepts_iso_date(self):
        self.assertEqual(validate_due_date("2026-07-05"), "2026-07-05")
        self.assertIsNone(validate_due_date(None))

    def test_normalise_tags_deduplicates(self):
        self.assertEqual(normalise_tags("API, api, frontend"), ["api", "frontend"])

    def test_normalise_blocked_by_deduplicates(self):
        self.assertEqual(normalise_blocked_by([2, 2, 3]), [2, 3])

    def test_validate_recurrence(self):
        self.assertEqual(validate_recurrence("daily"), "daily")
        self.assertIsNone(validate_recurrence(None))
        with self.assertRaisesRegex(ValueError, "Recurrence"):
            validate_recurrence("yearly")

    def test_recurrence_period_elapsed_daily(self):
        self.assertTrue(
            recurrence_period_elapsed(
                "daily",
                last_recurred_at=None,
                created_at="2026-07-04T10:00:00+00:00",
            )
        )


if __name__ == "__main__":
    unittest.main()