import unittest

from taskpulse.store import TaskStore


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


if __name__ == "__main__":
    unittest.main()
