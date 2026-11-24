"""Tests for deterministic CV coaching and DOCX export."""

from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cv_export import generate_cv_docx  # noqa: E402
from core.cv_insights import (  # noqa: E402
    analyse_job_ad,
    bullet_feedback,
    cover_letter,
    cv_strength,
    interview_questions,
)

PROFILE = {
    "name": "Jane Wanjiku Doe",
    "education": "Diploma in Information Technology",
    "location": "Nairobi",
    "experience": "ICT attachment",
    "career_interest": "ICT support",
    "skills": ["Excel", "Customer care"],
}

CV = {
    "phone": "0712 345 678",
    "email": "jane@example.com",
    "target_role": "ICT Support Officer",
    "summary": (
        "Early-career ICT professional with practical support experience and a "
        "focus on reliable customer service."
    ),
    "education": ["Kenya Certificate of Secondary Education (KCSE) - 2021"],
    "experience": [
        {
            "job_title": "ICT Intern",
            "organisation": "ABC Ltd",
            "location": "Nairobi",
            "start_date": "January 2025",
            "end_date": "Present",
            "responsibilities": [
                "Responsible for helping staff with computer issues",
                "Supported 20 staff with printer setup and documented fixes",
            ],
        }
    ],
    "skills": ["Excel", "Customer care", "Troubleshooting", "Communication"],
    "projects": ["Built a small inventory tracker"],
    "languages": ["English", "Kiswahili"],
    "referees": ["Available upon request"],
}

JOB_AD = (
    "We need an ICT support officer with Excel, troubleshooting, Windows, "
    "customer care and networking skills. Experience with databases is an advantage."
)

KNOWN = [
    "Excel",
    "Troubleshooting",
    "Windows",
    "Customer care",
    "Networking",
    "Database management",
]


class JobAdMatchTests(unittest.TestCase):
    def test_match_reports_present_and_missing_skills(self) -> None:
        result = analyse_job_ad(JOB_AD, PROFILE, CV, KNOWN)
        self.assertTrue(result["available"])
        self.assertIn("Excel", result["matched"])
        self.assertIn("Networking", result["missing"])
        self.assertEqual(result["score"], 60)
        self.assertFalse(result["fallback"])

    def test_match_does_not_modify_the_cv(self) -> None:
        before = dict(CV)
        skills_before = list(CV["skills"])
        analyse_job_ad(JOB_AD, PROFILE, CV, KNOWN + ["Coaching"])
        self.assertEqual(CV, before)
        self.assertEqual(CV["skills"], skills_before)

    def test_empty_advert_is_unavailable(self) -> None:
        self.assertFalse(analyse_job_ad("   ", PROFILE, CV, KNOWN)["available"])

    def test_fallback_terms_are_marked_for_review(self) -> None:
        result = analyse_job_ad(
            "We value punctuality, accuracy, teamwork and record keeping.",
            PROFILE,
            CV,
            [],
        )
        self.assertTrue(result["fallback"])
        self.assertIn("Do not add a keyword", result["note"])


class StrengthAndCoachingTests(unittest.TestCase):
    def test_strength_score_is_bounded_and_actionable(self) -> None:
        result = cv_strength(PROFILE, CV)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertTrue(result["fixes"])
        self.assertIn("not a guarantee", result["note"])

    def test_weak_bullet_is_rewritten_without_inventing_a_number(self) -> None:
        result = bullet_feedback("Responsible for helping staff with computer issues")
        self.assertEqual(result["suggestion"], "Supported staff with computer issues")
        self.assertNotIn("2", result["suggestion"])
        self.assertTrue(result["issues"])

    def test_cover_letter_uses_real_cv_fields_only(self) -> None:
        letter = cover_letter(PROFILE, CV)
        self.assertIn("Jane Wanjiku Doe", letter)
        self.assertIn("ICT Support Officer", letter)
        self.assertIn("jane@example.com", letter)
        self.assertIn("review this draft", letter)
        self.assertNotIn("Google", letter)

    def test_missing_target_role_does_not_duplicate_the_word_role(self) -> None:
        cv_without_target = {key: value for key, value in CV.items() if key != "target_role"}
        letter = cover_letter(PROFILE, cv_without_target)
        self.assertIn("apply for the advertised role.", letter)
        self.assertNotIn("role role", letter)
        questions = interview_questions(PROFILE, cv_without_target)
        self.assertIn(
            "Why are you interested in this role, and what makes you a suitable candidate?",
            questions,
        )
        self.assertFalse(any("this role role" in question for question in questions))

    def test_interview_questions_are_grounded_in_cv_data(self) -> None:
        questions = interview_questions(PROFILE, CV)
        self.assertTrue(any("ICT Intern" in question for question in questions))
        self.assertTrue(any("Excel" in question for question in questions))
        self.assertLessEqual(len(questions), 8)


class DocxExportTests(unittest.TestCase):
    def test_docx_is_a_valid_package_with_expected_text(self) -> None:
        data = generate_cv_docx(PROFILE, CV)
        package = zipfile.ZipFile(io.BytesIO(data))
        names = package.namelist()
        self.assertIn("word/document.xml", names)
        self.assertIn("[Content_Types].xml", names)
        for name in names:
            if name.endswith(".xml") or name.endswith(".rels"):
                ElementTree.fromstring(package.read(name))
        document = package.read("word/document.xml").decode("utf-8")
        self.assertIn("Jane Wanjiku Doe", document)
        self.assertIn("ICT Support Officer", document)
        self.assertIn("Created with KaziMsaada AI", document)


if __name__ == "__main__":
    unittest.main()
