import os
import unittest
from unittest.mock import patch

from coach.redact import redact


class RedactionTests(unittest.TestCase):
    def test_email_mobile_and_resident_number(self):
        with patch.dict(os.environ, {"REDACT_NAMES": ""}):
            text, counts = redact("메일 test.user@example.com 전화 010-1234-5678 주민번호 900101-1234567")
        self.assertEqual(text, "메일 [EMAIL] 전화 [PHONE] 주민번호 [RRN]")
        self.assertEqual(counts, {"[EMAIL]": 1, "[PHONE]": 1, "[RRN]": 1})

    def test_mobile_formats(self):
        with patch.dict(os.environ, {"REDACT_NAMES": ""}):
            for number in ("01012345678", "010 1234 5678", "010.1234.5678"):
                with self.subTest(number=number):
                    self.assertEqual(redact(number), ("[PHONE]", {"[PHONE]": 1}))

    def test_names_from_environment(self):
        with patch.dict(os.environ, {"REDACT_NAMES": " 김테스트, 이가상, "}):
            self.assertEqual(redact("김테스트와 이가상, 김테스트"),
                             ("[NAME]와 [NAME], [NAME]", {"[NAME]": 3}))
