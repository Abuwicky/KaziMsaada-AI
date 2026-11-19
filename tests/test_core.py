"""Core tests that use temporary databases only.

These tests never open or modify the real data/kazimsaada.db file.
"""

from __future__ import annotations

import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cv import (  # noqa: E402
    TEMPLATES,
    build_cv_content,
    build_cv_html,
    generate_cv_pdf,
    is_valid_email,
    is_valid_phone,
    list_saved_cvs,
    phone_digit_count,
    save_cv_bundle,
    validate_cv_contact_details,
)
from core.database import initialize_database, migrate_json_profiles  # noqa: E402
from core.profiles import (  # noqa: E402
    ProfileValidationError,
    create_profile,
    delete_profile_record,
    get_profile,
    load_profiles,
    normalize_skills,
    profile_completeness,
    search_profiles,
    update_profile_record,
)

SAMPLE_PROFILE = {
    "name": "Test Applicant",
    "education": "Diploma in Information Technology",
    "location": "Nairobi",
    "experience": "One year of ICT support attachment",
    "career_interest": "ICT support",
    "skills": ["Computer literacy", "Problem solving", "Customer care"],
}

SAMPLE_CV = {
    "phone": "0700 000 000",
    "email": "test@example.com",
    "target_role": "ICT Support Officer",
    "summary": "Early-career ICT professional with practical support experience.",
    "education": ["Kenya Certificate of Secondary Education"],
    "experience": [
        {
            "job_title": "ICT Support Assistant",
            "organisation": "Example Organisation",
            "location": "Nairobi",
            "start_date": "January 2025",
            "end_date": "Present",
            "responsibilities": ["Supported staff with hardware issues", "Documented fixes"],
        }
    ],
    "projects": ["Built a small inventory tracker"],
    "volunteering": ["Community digital literacy sessions"],
    "skills": ["Computer literacy", "Troubleshooting", "Customer care"],
    "certifications": ["Customer care short course"],
    "languages": ["English", "Kiswahili"],
    "referees": ["Available upon request"],
}


class TemporaryDatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "test.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()


class DatabaseSchemaTests(TemporaryDatabaseTest):
    def test_schema_created(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            connection.close()

        self.assertIn("job_seekers", tables)
        self.assertIn("migration_history", tables)

    def test_initial_database_is_empty(self) -> None:
        self.assertEqual(load_profiles(self.db_path), [])


class ProfileCrudTests(TemporaryDatabaseTest):
    def test_create_load_and_get_profile(self) -> None:
        created = create_profile(SAMPLE_PROFILE, db_path=self.db_path)

        self.assertTrue(created["profile_id"])
        self.assertEqual(created["name"], "Test Applicant")
        self.assertEqual(created["skills"], SAMPLE_PROFILE["skills"])

        profiles = load_profiles(self.db_path)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["profile_id"], created["profile_id"])
        self.assertEqual(get_profile(created["profile_id"], self.db_path), profiles[0])

    def test_update_does_not_duplicate(self) -> None:
        created = create_profile(SAMPLE_PROFILE, db_path=self.db_path)
        updated = dict(created)
        updated["name"] = "Updated Applicant"
        updated["skills"] = ["Computer literacy"]

        self.assertTrue(update_profile_record(updated, db_path=self.db_path))

        profiles = load_profiles(self.db_path)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["name"], "Updated Applicant")
        self.assertEqual(profiles[0]["skills"], ["Computer literacy"])

    def test_update_missing_profile_returns_false(self) -> None:
        missing = dict(SAMPLE_PROFILE)
        missing.update(
            {
                "profile_id": "00000000-0000-0000-0000-000000000000",
                "created_at": "2026-01-01T00:00:00+03:00",
            }
        )
        self.assertFalse(update_profile_record(missing, db_path=self.db_path))

    def test_delete_profile(self) -> None:
        created = create_profile(SAMPLE_PROFILE, db_path=self.db_path)

        self.assertTrue(delete_profile_record(created["profile_id"], db_path=self.db_path))
        self.assertIsNone(get_profile(created["profile_id"], self.db_path))
        self.assertEqual(load_profiles(self.db_path), [])

    def test_delete_missing_profile_returns_false(self) -> None:
        self.assertFalse(delete_profile_record("missing-id", db_path=self.db_path))

    def test_search_by_name_and_exact_id(self) -> None:
        created = create_profile(SAMPLE_PROFILE, db_path=self.db_path)

        self.assertEqual(len(search_profiles("applicant", self.db_path)), 1)
        self.assertEqual(len(search_profiles(created["profile_id"], self.db_path)), 1)
        self.assertEqual(search_profiles("no match", self.db_path), [])

    def test_validation_rejects_missing_required_fields(self) -> None:
        with self.assertRaises(ProfileValidationError) as context:
            create_profile({"name": "", "skills": []}, db_path=self.db_path)

        self.assertIn("name", context.exception.errors)
        self.assertIn("education", context.exception.errors)
        self.assertEqual(load_profiles(self.db_path), [])

    def test_blank_experience_is_normalised(self) -> None:
        data = dict(SAMPLE_PROFILE)
        data["experience"] = "   "
        created = create_profile(data, db_path=self.db_path)
        self.assertEqual(created["experience"], "No formal work experience yet")

    def test_skills_normalisation(self) -> None:
        self.assertEqual(
            normalize_skills("Python, python,  Data entry ,, "),
            ["Python", "Data entry"],
        )

    def test_completeness_uses_real_fields(self) -> None:
        self.assertEqual(profile_completeness(SAMPLE_PROFILE), 100)
        self.assertEqual(profile_completeness({}), 0)
        self.assertLess(profile_completeness({"name": "A"}), 100)


class JsonMigrationTests(TemporaryDatabaseTest):
    def _write_source(self, profiles: list) -> Path:
        path = self.root / "profiles.json"
        path.write_text(json.dumps(profiles), encoding="utf-8")
        return path

    def test_migration_imports_once_and_preserves_source(self) -> None:
        source = self._write_source(
            [
                {
                    "name": "Migration Test",
                    "education": "Certificate",
                    "location": "Kisumu",
                    "experience": "Volunteer work",
                    "career_interest": "Community work",
                    "skills": ["Listening", "Reporting"],
                }
            ]
        )
        before = source.read_text(encoding="utf-8")

        result = migrate_json_profiles(source, self.db_path)
        self.assertEqual(result["status"], "imported")
        self.assertEqual(result["imported"], 1)
        self.assertEqual(len(load_profiles(self.db_path)), 1)
        self.assertEqual(source.read_text(encoding="utf-8"), before)

        second = migrate_json_profiles(source, self.db_path)
        self.assertEqual(second["status"], "already_completed")
        self.assertEqual(len(load_profiles(self.db_path)), 1)

    def test_migration_missing_source(self) -> None:
        result = migrate_json_profiles(self.root / "missing.json", self.db_path)
        self.assertEqual(result["status"], "no_source")

    def test_migration_invalid_structure(self) -> None:
        source = self.root / "invalid.json"
        source.write_text('{"not": "a list"}', encoding="utf-8")

        result = migrate_json_profiles(source, self.db_path)
        self.assertEqual(result["status"], "invalid_source")
        self.assertEqual(load_profiles(self.db_path), [])

    def test_migration_invalid_json_reports_error(self) -> None:
        source = self.root / "broken.json"
        source.write_text("{broken", encoding="utf-8")

        result = migrate_json_profiles(source, self.db_path)
        self.assertEqual(result["status"], "source_error")
        self.assertTrue(result["error"])


class CvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = {
            "profile_id": "12345678-aaaa-bbbb-cccc-1234567890ab",
            **SAMPLE_PROFILE,
        }

    def test_content_contains_expected_sections(self) -> None:
        content = build_cv_content(self.profile, SAMPLE_CV)

        self.assertTrue(content.startswith("=" * 60))
        self.assertIn("TEST APPLICANT", content)
        self.assertIn("PROFESSIONAL SUMMARY", content)
        self.assertIn("EDUCATION", content)
        self.assertIn("WORK EXPERIENCE", content)
        self.assertIn("ICT SUPPORT ASSISTANT", content)
        self.assertIn("- Supported staff with hardware issues", content)
        self.assertIn("PROJECTS AND PRACTICAL EXPERIENCE", content)
        self.assertIn("REFEREES", content)
        self.assertTrue(content.rstrip().endswith("=" * 60))

    def test_html_preview_escapes_user_content(self) -> None:
        profile = dict(self.profile)
        profile["name"] = "<script>alert(1)</script>"
        html = build_cv_html(profile, SAMPLE_CV, "modern")

        lowered = html.lower()
        self.assertIn("&lt;script&gt;", lowered)
        self.assertNotIn("<script>alert(1)</script>", lowered)
        self.assertIn("hs-rule_accent", html)

    def test_pdf_generation_to_buffer(self) -> None:
        buffer = io.BytesIO()
        generate_cv_pdf(build_cv_content(self.profile, SAMPLE_CV), buffer, "classic")
        data = buffer.getvalue()

        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 1000)

    def test_all_templates_generate_pdf(self) -> None:
        for template in TEMPLATES:
            with self.subTest(template=template):
                buffer = io.BytesIO()
                generate_cv_pdf(build_cv_content(self.profile, SAMPLE_CV), buffer, template)
                self.assertTrue(buffer.getvalue().startswith(b"%PDF"))

    def test_every_template_has_project_metadata_and_html(self) -> None:
        for template, meta in TEMPLATES.items():
            with self.subTest(template=template):
                for field in (
                    "name",
                    "description",
                    "best_for",
                    "ats",
                    "accent",
                    "muted",
                    "layout",
                    "section_order",
                ):
                    self.assertTrue(meta.get(field), field)
                self.assertIn(meta["layout"], {"single", "sidebar"})
                self.assertIn(meta["ats"], {"Best", "Good", "Use with care"})
                self.assertRegex(meta["accent"], r"^#[0-9A-Fa-f]{6}$")
                self.assertRegex(meta["muted"], r"^#[0-9A-Fa-f]{6}$")
                html = build_cv_html(self.profile, SAMPLE_CV, template)
                self.assertIn("<!DOCTYPE html>", html)
                self.assertIn('class="sheet', html)
                if meta["layout"] == "sidebar":
                    self.assertIn("side-col", html)

    def test_save_bundle_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cv_dir = Path(temp_dir) / "cvs"
            result = save_cv_bundle(self.profile, SAMPLE_CV, "graduate", cv_dir=cv_dir)

            self.assertTrue(result["txt_path"].exists())
            self.assertTrue(result["pdf_path"].exists())
            self.assertIn("_graduate_", result["filename"])
            self.assertEqual(result["txt_path"].read_text(encoding="utf-8"), result["content"])

            records = list_saved_cvs(cv_dir)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["name"], result["pdf_path"].name)

    def test_repeated_saves_create_unique_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cv_dir = Path(temp_dir) / "cvs"
            first = save_cv_bundle(self.profile, SAMPLE_CV, "classic", cv_dir=cv_dir)
            second = save_cv_bundle(self.profile, SAMPLE_CV, "classic", cv_dir=cv_dir)

            self.assertNotEqual(first["filename"], second["filename"])
            self.assertEqual(len(list_saved_cvs(cv_dir)), 2)
            self.assertTrue(first["pdf_path"].exists())
            self.assertTrue(second["pdf_path"].exists())

    def test_save_failure_does_not_leave_partial_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cv_dir = Path(temp_dir) / "cvs"
            with mock.patch(
                "core.cv.generate_cv_pdf",
                side_effect=RuntimeError("simulated PDF failure"),
            ):
                with self.assertRaises(RuntimeError):
                    save_cv_bundle(self.profile, SAMPLE_CV, "classic", cv_dir=cv_dir)

            self.assertEqual(list(cv_dir.glob("*")), [])

    def test_string_cv_sections_are_split_into_items(self) -> None:
        cv_data = dict(SAMPLE_CV)
        cv_data["projects"] = "Inventory tracker\nDigital literacy session"
        cv_data["skills"] = "Python, Excel"
        content = build_cv_content(self.profile, cv_data)

        self.assertIn("- Inventory tracker", content)
        self.assertIn("- Digital literacy session", content)
        self.assertIn("- Python", content)
        self.assertIn("- Excel", content)

    def test_skills_with_commas_are_preserved_when_passed_as_a_list(self) -> None:
        cv_data = dict(SAMPLE_CV)
        cv_data["skills"] = ["Monitoring, evaluation and learning", "Excel"]
        content = build_cv_content(self.profile, cv_data)

        self.assertIn("- Monitoring, evaluation and learning", content)
        self.assertIn("- Excel", content)

    def test_multiple_experiences_and_no_experience(self) -> None:
        cv_data = dict(SAMPLE_CV)
        cv_data["experience"] = [
            SAMPLE_CV["experience"][0],
            {
                "job_title": "Volunteer Data Assistant",
                "organisation": "Community Office",
                "location": "Nairobi",
                "start_date": "January 2024",
                "end_date": "April 2024",
                "responsibilities": ["Entered survey records", "Prepared weekly summaries"],
            },
        ]
        content = build_cv_content(self.profile, cv_data)
        self.assertIn("ICT SUPPORT ASSISTANT", content)
        self.assertIn("VOLUNTEER DATA ASSISTANT", content)

        graduate_data = dict(SAMPLE_CV)
        graduate_data["experience"] = []
        graduate_content = build_cv_content(self.profile, graduate_data)
        self.assertNotIn("WORK EXPERIENCE", graduate_content)
        self.assertIn("EDUCATION", graduate_content)
        self.assertIn("PROJECTS AND PRACTICAL EXPERIENCE", graduate_content)
        self.assertIn("SKILLS", graduate_content)


class CvValidationTests(unittest.TestCase):
    def test_valid_contact_details(self) -> None:
        self.assertEqual(
            validate_cv_contact_details(
                "ICT Support Officer", "name@example.com", "0712 345 678"
            ),
            {},
        )

    def test_target_role_is_required(self) -> None:
        errors = validate_cv_contact_details("   ", "name@example.com", "0712345678")
        self.assertIn("target_role", errors)

    def test_valid_email_addresses(self) -> None:
        for value in (
            "name@example.com",
            "first.last+tag@example.co.ke",
            "user_name@sub.domain.org",
        ):
            with self.subTest(value=value):
                self.assertTrue(is_valid_email(value))

    def test_invalid_or_incomplete_email_addresses(self) -> None:
        for value in (
            "",
            "plain",
            "user@",
            "user@example",
            "user@.com",
            "user@example.",
            "user@@example.com",
            "user name@example.com",
            "user@example.c",
        ):
            with self.subTest(value=value):
                self.assertFalse(is_valid_email(value))
                errors = validate_cv_contact_details(
                    "ICT Support Officer", value, "0712345678"
                )
                self.assertIn("email", errors)

    def test_phone_validation_counts_digits(self) -> None:
        self.assertEqual(phone_digit_count("+254 712-345-678"), 12)
        self.assertTrue(is_valid_phone("+254 712-345-678"))
        self.assertTrue(is_valid_phone("0712 345 678"))
        self.assertFalse(is_valid_phone("123456"))
        self.assertFalse(is_valid_phone("phone only"))


class CliCompatibilityTests(unittest.TestCase):
    def test_main_reexports_shared_functions(self) -> None:
        import main

        self.assertEqual(main.APP_NAME, "KAZIMSAADA AI")
        self.assertIs(main.generate_cv_pdf, generate_cv_pdf)
        self.assertIs(main.build_cv_content, build_cv_content)
        self.assertTrue(callable(main.load_profiles))
        self.assertTrue(callable(main.save_profile))
        self.assertTrue(callable(main.initialize_database))
        self.assertTrue(callable(main.improve_cv))


if __name__ == "__main__":
    unittest.main()
