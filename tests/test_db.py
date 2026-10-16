import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crawler import db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        patched_path = patch.object(db, "DB_PATH", Path(temporary.name) / "jobs.sqlite")
        patched_path.start()
        self.addCleanup(patched_path.stop)
        self.con = db.connect()
        self.addCleanup(self.con.close)

    def job(self, source_id, title=None, source="test"):
        return dict(source=source, source_id=str(source_id),
                    url="https://example.invalid/jobs/" + str(source_id),
                    company="Test Company", title=title or "Backend " + str(source_id))

    def seed(self, count):
        for source_id in range(1, count + 1):
            db.upsert_job(self.con, self.job(source_id))

    def states(self):
        return {row["source_id"]: (row["status"], row["closed_at"])
                for row in self.con.execute("SELECT * FROM jobs WHERE source='test'")}

    def test_renamed_title_preserves_uid(self):
        self.assertTrue(db.upsert_job(self.con, self.job(1, "Backend Engineer")))
        original = self.con.execute("SELECT uid FROM jobs").fetchone()["uid"]
        self.assertFalse(db.upsert_job(self.con, self.job(1, "Senior Backend Engineer")))
        rows = self.con.execute("SELECT uid, title FROM jobs").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["uid"], original)
        self.assertEqual(rows[0]["title"], "Senior Backend Engineer")

    def test_empty_listing_does_not_close_jobs(self):
        self.seed(3)
        before = self.states()
        self.assertEqual(db.close_missing(self.con, "test", []), 0)
        self.assertEqual(self.states(), before)

    def test_more_than_half_missing_does_not_close_jobs(self):
        self.seed(6)
        before = self.states()
        self.assertEqual(db.close_missing(self.con, "test", [1, 2]), 0)
        self.assertEqual(self.states(), before)

    def test_tiny_board_two_of_three_missing_closes(self):
        # rule (crawler/db.py close_missing): boards with <4 open postings close normally
        self.seed(3)
        self.assertEqual(db.close_missing(self.con, "test", [1]), 2)

    def test_four_open_three_missing_refused(self):
        self.seed(4)
        before = self.states()
        self.assertEqual(db.close_missing(self.con, "test", [1]), 0)
        self.assertEqual(self.states(), before)

    def test_single_missing_job_is_closed(self):
        self.seed(3)
        db.upsert_job(self.con, self.job(4, source="other"))
        self.assertEqual(db.close_missing(self.con, "test", [1, 2]), 1)
        states = self.states()
        self.assertEqual(states["1"], ("open", None))
        self.assertEqual(states["2"], ("open", None))
        self.assertEqual(states["3"][0], "closed")
        self.assertIsNotNone(states["3"][1])
        other = self.con.execute("SELECT status, closed_at FROM jobs WHERE source='other'").fetchone()
        self.assertEqual(tuple(other), ("open", None))
        self.assertEqual(db.close_missing(self.con, "test", [1, 2]), 0)
