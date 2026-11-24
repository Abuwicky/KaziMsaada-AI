"""Owner isolation and privacy-control tests.

Every test uses a temporary SQLite database and a temporary CV folder. The real
``data`` directory is never touched.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cv import cv_file_stem  # noqa: E402
from core.cv_drafts import (  # noqa: E402
    delete_cv_draft,
    load_cv_draft,
    load_cv_draft_updated_at,
    save_cv_draft,
)
from core.database import initialize_database  # noqa: E402
from core.mentor_store import (  # noqa: E402
    create_availability,
    create_booking,
    create_mentor_application,
    get_booking,
    get_mentor_application,
    list_bookings_for_profile,
    list_mentor_applications,
    review_mentor_application,
)
from core.mentors import MentorNotFoundError  # noqa: E402
from core.privacy import delete_owner_data, export_owner_data  # noqa: E402
from core.profiles import (  # noqa: E402
    create_profile,
    get_profile,
    load_profiles,
)
from core.workspace import (  # noqa: E402
    MENTOR_DIRECTORY_OWNER_ID,
    WorkspaceOwnerNotSet,
    clear_current_owner_id,
    current_cv_dir,
    get_current_owner_id,
    owner_scope,
    set_strict_owner_mode,
)

PROFILE = {
    "name": "Alice Applicant",
    "education": "Diploma in Information Technology",
    "location": "Nairobi",
    "experience": "One year of ICT support",
    "career_interest": "ICT support",
    "skills": ["Computer literacy", "Problem solving"],
}

OTHER_PROFILE = {
    "name": "Bob Applicant",
    "education": "Bachelor of Commerce",
    "location": "Mombasa",
    "experience": "Customer service internship",
    "career_interest": "Customer service",
    "skills": ["Customer care", "Communication"],
}

APPLICATION = {
    "full_name": "Jane Mentor",
    "email": "jane.mentor@example.com",
    "professional_title": "Senior HR Business Partner",
    "industry": "Human resources",
    "specialisation": "Interview coaching",
    "areas_of_expertise": ["Interview coaching", "CV review"],
    "experience": "Ten years supporting graduate recruitment and interviews.",
    "biography": "I help early-career professionals prepare honest interview answers.",
    "qualifications": "Bachelor of Commerce (HR)",
    "languages": ["English", "Kiswahili"],
    "supporting_info": "Available in the evenings.",
    "avatar_url": "",
}


class PrivacyTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "test.db"
        self.cv_root = self.root / "cvs"
        initialize_database(self.db_path)
        self.cv_patch = patch("core.workspace.CV_DIR", self.cv_root)
        self.cv_patch.start()
        self.addCleanup(self.cv_patch.stop)
        set_strict_owner_mode(False)
        clear_current_owner_id()
        self.addCleanup(set_strict_owner_mode, False)
        self.addCleanup(clear_current_owner_id)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_profile(self, data=PROFILE):
        return create_profile(data, db_path=self.db_path)


class OwnerIsolationTests(PrivacyTestBase):
    def test_profiles_and_drafts_are_private_to_each_owner(self) -> None:
        with owner_scope("alice"):
            alice = self.make_profile()
            save_cv_draft(alice["profile_id"], {"target_role": "ICT Officer"}, self.db_path)

        with owner_scope("bob"):
            self.assertEqual(load_profiles(self.db_path), [])
            self.assertIsNone(get_profile(alice["profile_id"], self.db_path))
            self.assertEqual(load_cv_draft(alice["profile_id"], self.db_path), {})

        with owner_scope("alice"):
            self.assertEqual(len(load_profiles(self.db_path)), 1)
            self.assertEqual(
                load_cv_draft(alice["profile_id"], self.db_path)["target_role"],
                "ICT Officer",
            )

    def test_mentor_applications_are_private_but_admin_can_review(self) -> None:
        with owner_scope("alice"):
            profile = self.make_profile()
            application = create_mentor_application(
                APPLICATION,
                applicant_profile_id=profile["profile_id"],
                db_path=self.db_path,
            )

        with owner_scope("bob"):
            self.assertEqual(list_mentor_applications(db_path=self.db_path), [])
            with self.assertRaises(MentorNotFoundError):
                get_mentor_application(application["application_id"], db_path=self.db_path)

        self.assertEqual(
            len(list_mentor_applications(db_path=self.db_path, include_all=True)),
            1,
        )
        result = review_mentor_application(
            application["application_id"], "approved", db_path=self.db_path
        )
        self.assertIsNotNone(result["mentor"])

    def test_bookings_are_scoped_to_the_profile_owner(self) -> None:
        with owner_scope("alice"):
            profile = self.make_profile()
            application = create_mentor_application(
                APPLICATION,
                applicant_profile_id=profile["profile_id"],
                db_path=self.db_path,
            )
            approved = review_mentor_application(
                application["application_id"], "approved", db_path=self.db_path
            )
            mentor = approved["mentor"]
            start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            slot = create_availability(
                mentor["mentor_id"],
                start.isoformat(),
                60,
                db_path=self.db_path,
            )
            booking = create_booking(
                profile["profile_id"],
                mentor["mentor_id"],
                slot["slot_id"],
                "Interview practice",
                db_path=self.db_path,
            )

        with owner_scope("bob"):
            self.assertEqual(
                list_bookings_for_profile(profile["profile_id"], self.db_path), []
            )
            with self.assertRaises(MentorNotFoundError):
                get_booking(
                    booking["booking_id"],
                    profile_id=profile["profile_id"],
                    db_path=self.db_path,
                )

        with owner_scope("alice"):
            self.assertEqual(
                len(list_bookings_for_profile(profile["profile_id"], self.db_path)), 1
            )


class CvDraftTests(PrivacyTestBase):
    def test_draft_round_trip_and_timestamp(self) -> None:
        profile = self.make_profile()
        self.assertEqual(load_cv_draft(profile["profile_id"], self.db_path), {})
        save_cv_draft(
            profile["profile_id"],
            {"summary": "Saved text", "skills": ["Excel"]},
            self.db_path,
        )
        self.assertEqual(
            load_cv_draft(profile["profile_id"], self.db_path)["summary"],
            "Saved text",
        )
        self.assertIsNotNone(
            load_cv_draft_updated_at(profile["profile_id"], self.db_path)
        )

    def test_draft_requires_an_owned_profile(self) -> None:
        with owner_scope("alice"):
            alice = self.make_profile()
        with owner_scope("bob"):
            with self.assertRaises(Exception):
                save_cv_draft(alice["profile_id"], {"summary": "Nope"}, self.db_path)

    def test_draft_delete_only_removes_the_matching_owner(self) -> None:
        with owner_scope("alice"):
            alice = self.make_profile()
            save_cv_draft(alice["profile_id"], {"summary": "Alice"}, self.db_path)

        with owner_scope("bob"):
            self.assertFalse(delete_cv_draft(alice["profile_id"], self.db_path))

        with owner_scope("alice"):
            self.assertTrue(delete_cv_draft(alice["profile_id"], self.db_path))
            self.assertEqual(load_cv_draft(alice["profile_id"], self.db_path), {})


class PrivacyControlTests(PrivacyTestBase):
    def test_export_contains_only_the_current_owner(self) -> None:
        with owner_scope("alice"):
            alice = self.make_profile()
            save_cv_draft(alice["profile_id"], {"summary": "Alice draft"}, self.db_path)
        with owner_scope("bob"):
            bob = self.make_profile(OTHER_PROFILE)
            save_cv_draft(bob["profile_id"], {"summary": "Bob draft"}, self.db_path)

        with owner_scope("alice"):
            export = export_owner_data(db_path=self.db_path)

        self.assertEqual(len(export["profiles"]), 1)
        self.assertEqual(export["profiles"][0]["name"], "Alice Applicant")
        self.assertEqual(len(export["cv_drafts"]), 1)
        self.assertEqual(export["cv_drafts"][0]["draft"]["summary"], "Alice draft")
        self.assertNotIn("owner_id", export["profiles"][0])
        self.assertNotIn("draft_json", export["cv_drafts"][0])

    def test_delete_removes_owner_data_but_preserves_other_owners_and_mentors(self) -> None:
        with owner_scope("bob"):
            bob = self.make_profile(OTHER_PROFILE)

        with owner_scope("alice"):
            alice = self.make_profile()
            save_cv_draft(alice["profile_id"], {"summary": "Alice draft"}, self.db_path)
            alice_cv = current_cv_dir()
            alice_cv.mkdir(parents=True, exist_ok=True)
            (alice_cv / "alice.pdf").write_bytes(b"pdf")
            application = create_mentor_application(
                APPLICATION,
                applicant_profile_id=alice["profile_id"],
                db_path=self.db_path,
            )
            review_mentor_application(
                application["application_id"], "approved", db_path=self.db_path
            )

        with owner_scope("alice"):
            deleted = delete_owner_data(db_path=self.db_path)

        self.assertEqual(deleted["profiles"], 1)
        self.assertEqual(deleted["cv_drafts"], 1)
        self.assertEqual(deleted["cv_files"], 1)
        self.assertFalse((alice_cv / "alice.pdf").exists())

        with owner_scope("alice"):
            self.assertEqual(load_profiles(self.db_path), [])
        with owner_scope("bob"):
            self.assertEqual(len(load_profiles(self.db_path)), 1)

        connection = sqlite3.connect(self.db_path)
        try:
            connection.row_factory = sqlite3.Row
            app_row = connection.execute(
                "SELECT owner_id, applicant_profile_id, email, supporting_info "
                "FROM mentor_applications WHERE application_id = ?",
                (application["application_id"],),
            ).fetchone()
            self.assertEqual(app_row["owner_id"], MENTOR_DIRECTORY_OWNER_ID)
            self.assertIsNone(app_row["applicant_profile_id"])
            self.assertEqual(app_row["supporting_info"], "")
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM mentor_profiles").fetchone()[0],
                1,
            )
        finally:
            connection.close()


class MigrationTests(PrivacyTestBase):
    def test_existing_rows_receive_local_owner(self) -> None:
        old_db = self.root / "old.db"
        connection = sqlite3.connect(old_db)
        try:
            connection.execute(
                """
                CREATE TABLE job_seekers (
                    profile_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    education TEXT NOT NULL,
                    location TEXT NOT NULL,
                    experience TEXT NOT NULL,
                    career_interest TEXT NOT NULL,
                    skills TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
                """
            )
            connection.execute(
                """
                INSERT INTO job_seekers VALUES (
                    'old-profile', 'Old Applicant', 'Diploma', 'Nairobi',
                    'Experience', 'ICT', '[]', '2026-01-01', NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

        initialize_database(old_db)

        connection = sqlite3.connect(old_db)
        try:
            row = connection.execute(
                "SELECT owner_id FROM job_seekers WHERE profile_id = 'old-profile'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row[0], "local")


class StrictOwnerModeTests(PrivacyTestBase):
    def test_non_strict_mode_defaults_to_local(self) -> None:
        clear_current_owner_id()
        set_strict_owner_mode(False)
        self.assertEqual(get_current_owner_id(), "local")

    def test_strict_mode_blocks_access_without_a_signed_in_owner(self) -> None:
        clear_current_owner_id()
        set_strict_owner_mode(True)
        with self.assertRaises(WorkspaceOwnerNotSet):
            get_current_owner_id()
        with self.assertRaises(WorkspaceOwnerNotSet):
            load_profiles(self.db_path)

    def test_owner_scope_works_in_strict_mode_and_clears_afterwards(self) -> None:
        set_strict_owner_mode(True)
        clear_current_owner_id()
        with owner_scope("alice"):
            self.assertEqual(get_current_owner_id(), "alice")
        with self.assertRaises(WorkspaceOwnerNotSet):
            get_current_owner_id()


class CvFilenameTests(unittest.TestCase):
    def test_filename_is_professional_and_safe(self) -> None:
        stem = cv_file_stem(
            {"name": "Jane Wanjiku Doe"},
            {"target_role": "ICT Support Officer / Intern"},
        )
        self.assertEqual(stem, "Jane_Wanjiku_Doe_ICT_Support_Officer_Intern_CV")
        self.assertNotIn("/", stem)
        self.assertNotIn(" ", stem)


if __name__ == "__main__":
    unittest.main()
