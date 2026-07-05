import json
import tempfile
import unittest
from pathlib import Path

from taskpulse.store import (
    TaskStore,
    create_default_store,
    create_store,
    normalise_tags,
    validate_due_date,
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


if __name__ == "__main__":
    unittest.main()