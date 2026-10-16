import unittest

from coach.review import validate


class ReviewValidationTests(unittest.TestCase):
    def setUp(self):
        self.pack = {"resume": {"text": "API 성능 개선\n서비스 운영 자동화"},
                     "mentor": {"principles": [{"id": "mentor-001"}]}}

    def check_issue(self, **changes):
        issue = dict(resume_quote="API 성능 개선", problem="측정 결과가 필요합니다",
                     fix="성능 개선", evidence_type="의견", evidence="", severity="medium")
        issue.update(changes)
        return validate({"issues": [issue]}, self.pack)["checks"][0]["fails"]

    def test_invented_numbers_with_units_are_flagged(self):
        self.assertEqual(self.check_issue(fix="응답 시간 800ms→240ms"),
                         ["invented_numbers:['240', '800']"])

    def test_measurement_placeholder_is_allowed(self):
        self.assertEqual(self.check_issue(fix="p95 [측정값]ms"), [])

    def test_quote_stitched_across_resume_lines(self):
        self.assertEqual(self.check_issue(
            resume_quote="API 성능 개선 / 서비스 운영 자동화"), [])

    def test_unknown_mentor_id_is_flagged(self):
        self.assertEqual(self.check_issue(evidence_type="멘토", evidence="mentor-999"),
                         ["mentor_id_unknown"])

    def test_known_mentor_id_is_allowed(self):
        self.assertEqual(self.check_issue(evidence_type="멘토", evidence="mentor-001"), [])
