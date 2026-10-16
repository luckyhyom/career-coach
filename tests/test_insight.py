import unittest

from crawler.insight import quote_in, strip_bilingual


class QuoteTests(unittest.TestCase):
    def test_full_quote_is_required(self):
        normalized_text = "buildreliableserviceswithpython"
        self.assertTrue(quote_in("Build reliable services", normalized_text))
        self.assertFalse(quote_in("Build reliable services with Java", normalized_text))

    def test_trailing_ellipsis_allows_truncation(self):
        for suffix in ("…", "...", "…  "):
            with self.subTest(suffix=suffix):
                self.assertTrue(quote_in("Build reliable services" + suffix,
                                         "buildreliableserviceswithpython"))

    def test_empty_quote_is_rejected(self):
        self.assertFalse(quote_in("", "buildreliableservices"))
        self.assertFalse(quote_in("…", "buildreliableservices"))


class BilingualTests(unittest.TestCase):
    def assert_english_removed(self, korean_body):
        korean = "English text will follow Korean\n" + korean_body
        text = korean + "\nCompany Introduction\nWe build reliable services."
        self.assertEqual(strip_bilingual(text), korean)

    def test_english_removed_after_long_korean_body(self):
        self.assert_english_removed("\n".join(["안정적인 서비스를 개발하고 운영합니다."] * 20))

    def test_english_removed_after_short_korean_body(self):
        self.assert_english_removed("백엔드 개발자를 모집합니다.")

    def test_without_marker_is_unchanged(self):
        text = "한국어 소개\nCompany Introduction\nEnglish content"
        self.assertEqual(strip_bilingual(text), text)
