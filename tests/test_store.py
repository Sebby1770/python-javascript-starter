import json
import tempfile
import unittest
from pathlib import Path

from taskpulse.store import TaskStore, create_default_store


class TaskStoreTest(unittest.TestCase):
    def test_add_task_trims_title_and_sets_defaults(self):
        store = TaskStore()

        task = store.add_task(title="  Draft README  ")

        self.assertEqual(task["id"], 1)
        self.assertEqual(task["title"], "Draft README")
        self.assertEqual(task["owner"], "Unassigned")
        self.assertEqual(task["priority"], "medium")
        self.assertFalse(task["done"])

    def test_rejects_blank_titles(self):
        store = TaskStore()

        with self.assertRaisesRegex(ValueError, "title"):
            store.add_task(title=" ")

    def test_rejects_invalid_priority(self):
        store = TaskStore()

        with self.assertRaisesRegex(ValueError, "Priority"):
            store.add_task(title="Ship", priority="urgent")

    def test_lists_tasks_in_creation_order(self):
        store = TaskStore()
        store.add_task(title="First")
        store.add_task(title="Second", priority="high")

        self.assertEqual(
            [task["title"] for task in store.list_tasks()],
            ["First", "Second"],
        )

    def test_toggle_task_flips_done_state(self):
        store = TaskStore()
        created = store.add_task(title="Toggle me")

        toggled = store.toggle_task(created["id"])
        self.assertTrue(toggled["done"])

        toggled_again = store.toggle_task(created["id"])
        self.assertFalse(toggled_again["done"])

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
            },
        )

        self.assertEqual(updated["title"], "Updated")
        self.assertEqual(updated["owner"], "Team")
        self.assertEqual(updated["priority"], "high")
        self.assertEqual(updated["minutes"], 45)
        self.assertTrue(updated["done"])

    def test_update_task_rejects_invalid_values(self):
        store = TaskStore()
        created = store.add_task(title="Valid")

        with self.assertRaisesRegex(ValueError, "title"):
            store.update_task(created["id"], {"title": "   "})

        with self.assertRaisesRegex(ValueError, "Priority"):
            store.update_task(created["id"], {"priority": "urgent"})

        with self.assertRaisesRegex(ValueError, "Minutes"):
            store.update_task(created["id"], {"minutes": 0})

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

    def test_persists_tasks_to_json_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "tasks.json"
            store = TaskStore(data_path=data_path)
            store.add_task(title="Persisted", owner="Seb", priority="high", minutes=40)

            reloaded = TaskStore(data_path=data_path)
            reloaded.load_from_file(data_path)
            tasks = reloaded.list_tasks()

            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["title"], "Persisted")
            self.assertEqual(tasks[0]["owner"], "Seb")
            self.assertEqual(tasks[0]["priority"], "high")
            self.assertEqual(tasks[0]["minutes"], 40)

            saved = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual(saved[0]["title"], "Persisted")

    def test_create_default_store_seeds_data_when_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = Path(temp_dir) / "tasks.json"
            store = create_default_store(data_path)

            tasks = store.list_tasks()
            self.assertEqual(len(tasks), 3)
            self.assertTrue(data_path.exists())


if __name__ == "__main__":
    unittest.main()