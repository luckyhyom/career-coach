import unittest
from datetime import date
from unittest.mock import patch

from crawler.population import tier


class TierTests(unittest.TestCase):
    def test_posting_date_tiers(self):
        with patch("crawler.population.date") as clock:
            clock.today.return_value = date(2026, 10, 16)
            for posted_at, expected in [
                ("2026-10-16", "recent"),
                ("2026-09-16", "recent"),
                ("2026-09-15", "open_older"),
                (None, "unknown_date"),
                ("", "unknown_date"),
            ]:
                with self.subTest(posted_at=posted_at):
                    self.assertEqual(tier({"posted_at": posted_at}, 30), expected)
