import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from crawler import refresh


class RefreshTests(unittest.TestCase):
    def db(self, rows):
        d = Path(tempfile.mkdtemp()) / "jobs.sqlite"
        con = sqlite3.connect(d)
        con.execute("CREATE TABLE runs (started_at TEXT, site TEXT, requests INTEGER, cache_hits INTEGER, new_jobs INTEGER, status TEXT)")
        con.executemany("INSERT INTO runs VALUES (?,?,0,0,0,?)", rows)
        con.commit()
        return d

    def test_no_db_is_stale(self):
        with mock.patch.object(refresh, "DB", Path(tempfile.mkdtemp()) / "none.sqlite"):
            self.assertIsNone(refresh.last_crawl())
            self.assertTrue(refresh.is_stale())

    def test_only_ok_runs_count(self):
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=3)).isoformat(timespec="seconds")
        d = self.db([(old, "rallit", "ok"), (now.isoformat(timespec="seconds"), "remember", "aborted: 403")])
        with mock.patch.object(refresh, "DB", d):
            self.assertEqual(refresh.last_crawl(), (now - timedelta(days=3)).astimezone().date())
            self.assertTrue(refresh.is_stale())

    def test_crawled_today_is_fresh(self):
        d = self.db([(datetime.now(timezone.utc).isoformat(timespec="seconds"), "ats", "ok")])
        with mock.patch.object(refresh, "DB", d):
            self.assertFalse(refresh.is_stale(date.today()))

    def test_disabled_never_refreshes(self):
        with mock.patch.object(refresh, "refresh") as r:
            refresh.ensure_fresh(enabled=False)
            r.assert_not_called()


if __name__ == "__main__":
    unittest.main()
