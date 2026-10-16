import json
import unittest

from crawler.extract import extract_row, load_skill_patterns, parse_years


class YearsTests(unittest.TestCase):
    def test_experience_requirements(self):
        for text, expected in [
            ("경력 3년 이상", (3, None)),
            ("1~3년", (1, 3)),
            ("8 years of professional software development experience", (8, None)),
            ("10+ years of experience, 5+ years of backend experience", (10, None)),
            ("신입", (0, None)),
            ("함께 서비스를 개발할 분", (None, None)),
            ("", (None, None)),
        ]:
            with self.subTest(text=text):
                self.assertEqual(parse_years(text), expected)


class SkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = load_skill_patterns()

    def skills(self, description):
        row = dict(title="개발자", description=description, qualifications=None,
                   preferred=None, source_skills="[]", experience=None, steps="[]")
        return json.loads(extract_row(row, self.patterns)["skills"])

    def test_msa_adjacent_to_korean(self):
        self.assertIn("MSA", self.skills("MSA기반 서비스"))

    def test_node_does_not_imply_javascript(self):
        skills = self.skills("Node.js")
        self.assertIn("Node.js", skills)
        self.assertNotIn("JavaScript", skills)

    def test_disability_preference_is_not_incident_response(self):
        self.assertNotIn("장애 대응", self.skills("장애인 우대"))
        self.assertIn("장애 대응", self.skills("장애 대응 경험"))

    def test_gender_expression_is_not_express(self):
        self.assertNotIn("Express", self.skills("gender expression"))
        self.assertIn("Express", self.skills("Express"))
