import unittest
from datetime import date

from taskpulse.nlp import parse_due_token, parse_task_text


class NlpTest(unittest.TestCase):
    def test_parse_full_example(self):
        reference = date(2026, 7, 5)
        parsed = parse_task_text(
            "high priority api task for Seb due Friday 30 min #backend #release",
            reference=reference,
        )

        self.assertEqual(parsed["title"], "api task")
        self.assertEqual(parsed["owner"], "Seb")
        self.assertEqual(parsed["priority"], "high")
        self.assertEqual(parsed["minutes"], 30)
        self.assertEqual(parsed["due_date"], "2026-07-10")
        self.assertEqual(parsed["tags"], ["backend", "release"])

    def test_parse_minimal_text(self):
        parsed = parse_task_text("Write changelog")

        self.assertEqual(parsed["title"], "Write changelog")
        self.assertEqual(parsed["owner"], "Unassigned")
        self.assertEqual(parsed["priority"], "medium")
        self.assertEqual(parsed["minutes"], 25)
        self.assertIsNone(parsed["due_date"])
        self.assertEqual(parsed["tags"], [])

    def test_parse_due_today_and_tomorrow(self):
        reference = date(2026, 7, 5)
        today = parse_task_text("ship release due today", reference=reference)
        tomorrow = parse_task_text("ship release due tomorrow", reference=reference)

        self.assertEqual(today["due_date"], "2026-07-05")
        self.assertEqual(tomorrow["due_date"], "2026-07-06")

    def test_parse_owner_explicit(self):
        parsed = parse_task_text("owner: Codex polish docs")

        self.assertEqual(parsed["owner"], "Codex")
        self.assertEqual(parsed["title"], "polish docs")

    def test_parse_rejects_empty_text(self):
        with self.assertRaisesRegex(ValueError, "required"):
            parse_task_text("   ")

    def test_parse_due_token_iso_date(self):
        self.assertEqual(parse_due_token("2026-12-01"), "2026-12-01")


if __name__ == "__main__":
    unittest.main()