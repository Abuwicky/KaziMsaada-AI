"""Tests for the Mentor Meeting Centre.

All tests use temporary SQLite databases. The real data/kazimsaada.db file is
never opened by this module.
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

from core.database import initialize_database  # noqa: E402
from core.mentor_access import (  # noqa: E402
    admin_access_configured,
    generate_access_code,
    hash_access_code,
    verify_access_code,
    verify_admin_access,
)
from core.mentor_store import (  # noqa: E402
    authenticate_mentor,
    cancel_booking,
    clear_reschedule_request,
    complete_booking,
    confirm_booking,
    create_availability,
    create_booking,
    create_mentor_application,
    get_booking,
    get_feedback,
    get_mentor_application,
    get_mentor_by_application,
    get_mentor_workspace,
    get_public_mentor,
    list_applications_for_profile,
    list_bookings_for_mentor,
    list_bookings_for_profile,
    list_mentor_applications,
    list_mentor_availability,
    list_open_slots,
    list_public_industries,
    list_public_mentors,
    reject_booking,
    remove_availability,
    request_reschedule,
    review_mentor_application,
    rotate_mentor_access_code,
    submit_feedback,
    update_availability,
    update_meeting_link,
    update_mentor_profile,
    update_mentor_recommendations,
)
from core.mentors import (  # noqa: E402
    BOOKING_CANCELLED,
    BOOKING_COMPLETED,
    BOOKING_CONFIRMED,
    BOOKING_PENDING,
    BOOKING_REJECTED,
    MentorConflictError,
    MentorNotFoundError,
    MentorPermissionError,
    MentorValidationError,
    format_nairobi,
    nairobi_to_utc,
    to_utc_iso,
)
from core.profiles import create_profile, delete_profile_record  # noqa: E402

SAMPLE_PROFILE = {
    "name": "Amani Wanjiku",
    "education": "Diploma in Business Management",
    "location": "Nairobi",
    "experience": "Two years of customer service experience",
    "career_interest": "Customer service",
    "skills": ["Customer care", "Communication"],
}
OTHER_PROFILE = {
    "name": "Brian Otieno",
    "education": "BSc Computer Science",
    "location": "Kisumu",
    "experience": "Graduate software projects",
    "career_interest": "Software development",
    "skills": ["Problem solving", "Teamwork"],
}

APPLICATION = {
    "full_name": "Jane Mentor",
    "email": "jane.mentor@example.com",
    "professional_title": "Senior HR Business Partner",
    "industry": "Human resources",
    "specialisation": "Interview coaching",
    "areas_of_expertise": ["Interview coaching", "CV review", "Career planning"],
    "experience": (
        "Ten years supporting graduate recruitment, interview panels and "
        "career development programmes."
    ),
    "biography": (
        "I help early-career professionals prepare structured, honest interview "
        "answers and understand what employers are assessing."
    ),
    "qualifications": "Bachelor of Commerce (HR), CIPD certificate",
    "languages": ["English", "Kiswahili"],
    "supporting_info": "Available for virtual sessions in the evenings.",
    "avatar_url": "",
}


class MentorTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "test.db"
        initialize_database(self.db_path)
        self.profile = create_profile(SAMPLE_PROFILE, db_path=self.db_path)
        self.other_profile = create_profile(OTHER_PROFILE, db_path=self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def apply(self, **overrides):
        data = dict(APPLICATION)
        data.update(overrides)
        return create_mentor_application(
            data,
            applicant_profile_id=self.profile["profile_id"],
            db_path=self.db_path,
        )

    def approved_mentor(self, **overrides):
        application = self.apply(**overrides)
        result = review_mentor_application(
            application["application_id"],
            "approved",
            db_path=self.db_path,
        )
        return result

    def make_slot(self, mentor_id: str, *, days: int = 2, hour: int = 9, duration: int = 60):
        start = (datetime.now(timezone.utc) + timedelta(days=days)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        return create_availability(
            mentor_id,
            to_utc_iso(start),
            duration,
            db_path=self.db_path,
        )

    def book(self, mentor_id: str, slot_id: str, profile: dict | None = None):
        profile = profile or self.profile
        return create_booking(
            profile["profile_id"],
            mentor_id,
            slot_id,
            "I need help preparing for an interview and explaining my experience.",
            "Customer service officer",
            db_path=self.db_path,
        )

    def confirmed_booking(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        slot = self.make_slot(mentor["mentor_id"])
        booking = self.book(mentor["mentor_id"], slot["slot_id"])
        confirmed = confirm_booking(
            booking["booking_id"], mentor["mentor_id"], db_path=self.db_path
        )
        return result, slot, confirmed


class MentorApplicationTests(MentorTestBase):
    def test_application_submission_and_profile_link(self):
        application = self.apply()
        self.assertEqual(application["status"], "pending")
        self.assertEqual(application["email"], "jane.mentor@example.com")
        self.assertEqual(
            application["areas_of_expertise"],
            ["Interview coaching", "CV review", "Career planning"],
        )
        self.assertEqual(
            list_applications_for_profile(
                self.profile["profile_id"], db_path=self.db_path
            )[0]["application_id"],
            application["application_id"],
        )
        self.assertIsNotNone(
            get_mentor_application(application["application_id"], db_path=self.db_path)
        )

    def test_duplicate_pending_application_is_rejected(self):
        self.apply()
        with self.assertRaises(MentorConflictError):
            self.apply()

    def test_rejected_applicant_can_reapply(self):
        first = self.apply()
        review_mentor_application(
            first["application_id"], "rejected", "Need more detail", db_path=self.db_path
        )
        second = self.apply()
        self.assertEqual(second["status"], "pending")

    def test_approval_creates_public_mentor_and_one_time_code(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        self.assertTrue(result["access_code"].startswith("KM-MENTOR-"))
        self.assertIsNotNone(mentor)
        public = get_public_mentor(mentor["mentor_id"], db_path=self.db_path)
        self.assertIsNotNone(public)
        self.assertEqual(public["full_name"], "Jane Mentor")
        self.assertNotIn("access_code", public)
        self.assertNotIn("email", public)
        self.assertEqual(public["duration_options"], [30, 45, 60])
        self.assertEqual(
            get_mentor_application(result["application"]["application_id"], db_path=self.db_path)[
                "status"
            ],
            "approved",
        )

    def test_rejection_never_creates_a_bookable_mentor(self):
        application = self.apply()
        result = review_mentor_application(
            application["application_id"],
            "rejected",
            "Credentials could not be confirmed",
            db_path=self.db_path,
        )
        self.assertIsNone(result["mentor"])
        self.assertIsNone(result["access_code"])
        self.assertEqual(list_public_mentors(db_path=self.db_path), [])
        self.assertEqual(
            get_mentor_application(application["application_id"], db_path=self.db_path)[
                "status"
            ],
            "rejected",
        )

    def test_application_cannot_be_reviewed_twice(self):
        application = self.apply()
        review_mentor_application(
            application["application_id"], "approved", db_path=self.db_path
        )
        with self.assertRaises(MentorConflictError):
            review_mentor_application(
                application["application_id"], "rejected", db_path=self.db_path
            )

    def test_public_directory_filters_and_hides_unapproved(self):
        approved = self.approved_mentor()
        pending = self.apply(
            email="pending@example.com",
            full_name="Pending Mentor",
        )
        self.assertEqual(len(list_public_mentors(db_path=self.db_path)), 1)
        self.assertEqual(
            list_public_mentors("Human", db_path=self.db_path)[0]["mentor_id"],
            approved["mentor"]["mentor_id"],
        )
        self.assertEqual(
            list_public_mentors(industry="Human resources", db_path=self.db_path)[0][
                "mentor_id"
            ],
            approved["mentor"]["mentor_id"],
        )
        self.assertEqual(
            list_public_mentors("No such skill", db_path=self.db_path), []
        )
        self.assertIn("Human resources", list_public_industries(db_path=self.db_path))
        self.assertEqual(
            get_public_mentor(pending["application_id"], db_path=self.db_path), None
        )

    def test_mentor_profile_update_is_visible_publicly(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        updated = update_mentor_profile(
            mentor["mentor_id"],
            {
                **mentor,
                "professional_title": "Lead Interview Coach",
                "coaching_areas": ["Interview coaching", "Salary negotiation"],
                "duration_options": [30, 60],
            },
            db_path=self.db_path,
        )
        self.assertEqual(updated["professional_title"], "Lead Interview Coach")
        public = get_public_mentor(mentor["mentor_id"], db_path=self.db_path)
        self.assertEqual(public["coaching_areas"], ["Interview coaching", "Salary negotiation"])
        self.assertEqual(public["duration_options"], [30, 60])

    def test_mentor_access_code_authentication_and_rotation(self):
        result = self.approved_mentor()
        mentor_id = result["mentor"]["mentor_id"]
        self.assertIsNotNone(
            authenticate_mentor(result["access_code"], db_path=self.db_path)
        )
        self.assertIsNone(authenticate_mentor("wrong-code", db_path=self.db_path))
        replacement = rotate_mentor_access_code(mentor_id, db_path=self.db_path)
        self.assertIsNone(
            authenticate_mentor(result["access_code"], db_path=self.db_path)
        )
        self.assertEqual(
            authenticate_mentor(replacement, db_path=self.db_path)["mentor_id"],
            mentor_id,
        )
        self.assertEqual(
            get_mentor_by_application(
                result["application"]["application_id"], db_path=self.db_path
            )["mentor_id"],
            mentor_id,
        )


class MentorAvailabilityTests(MentorTestBase):
    def test_availability_create_list_and_remove(self):
        mentor = self.approved_mentor()["mentor"]
        slot = self.make_slot(mentor["mentor_id"])
        self.assertEqual(slot["status"], "open")
        self.assertEqual(
            list_open_slots(mentor["mentor_id"], db_path=self.db_path)[0]["slot_id"],
            slot["slot_id"],
        )
        self.assertEqual(
            len(
                list_mentor_availability(
                    mentor["mentor_id"], include_past=False, db_path=self.db_path
                )
            ),
            1,
        )
        remove_availability(
            mentor["mentor_id"], slot["slot_id"], db_path=self.db_path
        )
        self.assertEqual(list_open_slots(mentor["mentor_id"], db_path=self.db_path), [])

    def test_availability_rejects_overlap_and_bad_duration(self):
        mentor = self.approved_mentor()["mentor"]
        start = (datetime.now(timezone.utc) + timedelta(days=3)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        create_availability(
            mentor["mentor_id"], to_utc_iso(start), 60, db_path=self.db_path
        )
        with self.assertRaises(MentorConflictError):
            create_availability(
                mentor["mentor_id"],
                to_utc_iso(start + timedelta(minutes=30)),
                60,
                db_path=self.db_path,
            )
        with self.assertRaises(MentorValidationError):
            create_availability(
                mentor["mentor_id"],
                to_utc_iso(start + timedelta(hours=2)),
                75,
                db_path=self.db_path,
            )

    def test_availability_update_and_booked_slot_protection(self):
        mentor = self.approved_mentor()["mentor"]
        slot = self.make_slot(mentor["mentor_id"], hour=9)
        new_start = (datetime.now(timezone.utc) + timedelta(days=4)).replace(
            hour=11, minute=0, second=0, microsecond=0
        )
        updated = update_availability(
            mentor["mentor_id"],
            slot["slot_id"],
            to_utc_iso(new_start),
            30,
            db_path=self.db_path,
        )
        self.assertEqual(updated["duration_minutes"], 30)
        self.assertEqual(updated["start_at_utc"], to_utc_iso(new_start))
        self.book(mentor["mentor_id"], slot["slot_id"])
        with self.assertRaises(MentorConflictError):
            remove_availability(
                mentor["mentor_id"], slot["slot_id"], db_path=self.db_path
            )
        with self.assertRaises(MentorConflictError):
            update_availability(
                mentor["mentor_id"],
                slot["slot_id"],
                to_utc_iso(new_start + timedelta(days=1)),
                30,
                db_path=self.db_path,
            )

    def test_slot_must_be_in_the_future(self):
        mentor = self.approved_mentor()["mentor"]
        with self.assertRaises(MentorValidationError):
            create_availability(
                mentor["mentor_id"],
                to_utc_iso(datetime.now(timezone.utc) - timedelta(days=1)),
                30,
                db_path=self.db_path,
            )


class MentorBookingTests(MentorTestBase):
    def test_successful_booking_and_confirmation(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        slot = self.make_slot(mentor["mentor_id"])
        booking = self.book(mentor["mentor_id"], slot["slot_id"])
        self.assertEqual(booking["status"], BOOKING_PENDING)
        self.assertTrue(booking["booking_reference"].startswith("KM-"))
        self.assertEqual(booking["mentor_name"], "Jane Mentor")
        self.assertEqual(booking["duration_minutes"], 60)
        confirmed = confirm_booking(
            booking["booking_id"], mentor["mentor_id"], db_path=self.db_path
        )
        self.assertEqual(confirmed["status"], BOOKING_CONFIRMED)
        self.assertIsNotNone(confirmed["confirmed_at"])

    def test_double_booking_is_prevented(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        slot = self.make_slot(mentor["mentor_id"])
        self.book(mentor["mentor_id"], slot["slot_id"])
        with self.assertRaises(MentorConflictError):
            self.book(mentor["mentor_id"], slot["slot_id"], self.other_profile)

    def test_duplicate_submission_is_prevented(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        slot = self.make_slot(mentor["mentor_id"])
        self.book(mentor["mentor_id"], slot["slot_id"])
        with self.assertRaises(MentorConflictError):
            self.book(mentor["mentor_id"], slot["slot_id"])

    def test_booking_rejection_reopens_slot(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        slot = self.make_slot(mentor["mentor_id"])
        booking = self.book(mentor["mentor_id"], slot["slot_id"])
        rejected = reject_booking(
            booking["booking_id"], mentor["mentor_id"], "Not available", db_path=self.db_path
        )
        self.assertEqual(rejected["status"], BOOKING_REJECTED)
        self.assertEqual(
            list_open_slots(mentor["mentor_id"], db_path=self.db_path)[0]["slot_id"],
            slot["slot_id"],
        )

    def test_booking_cancellation_by_job_seeker_and_mentor(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        slot = self.make_slot(mentor["mentor_id"])
        booking = self.book(mentor["mentor_id"], slot["slot_id"])
        cancelled = cancel_booking(
            booking["booking_id"],
            profile_id=self.profile["profile_id"],
            reason="Schedule changed",
            db_path=self.db_path,
        )
        self.assertEqual(cancelled["status"], BOOKING_CANCELLED)
        self.assertEqual(
            list_open_slots(mentor["mentor_id"], db_path=self.db_path)[0]["slot_id"],
            slot["slot_id"],
        )

        slot_two = self.make_slot(mentor["mentor_id"], days=4, hour=10)
        second = self.book(mentor["mentor_id"], slot_two["slot_id"])
        cancel_booking(
            second["booking_id"], mentor_id=mentor["mentor_id"], db_path=self.db_path
        )
        self.assertEqual(
            get_booking(
                second["booking_id"],
                mentor_id=mentor["mentor_id"],
                db_path=self.db_path,
            )["status"],
            BOOKING_CANCELLED,
        )

    def test_profile_isolation_and_mentor_permissions(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        slot = self.make_slot(mentor["mentor_id"])
        booking = self.book(mentor["mentor_id"], slot["slot_id"])
        with self.assertRaises(MentorNotFoundError):
            get_booking(
                booking["booking_id"],
                profile_id=self.other_profile["profile_id"],
                db_path=self.db_path,
            )
        with self.assertRaises(MentorNotFoundError):
            confirm_booking(
                booking["booking_id"], "another-mentor", db_path=self.db_path
            )
        with self.assertRaises(MentorPermissionError):
            get_booking(booking["booking_id"], db_path=self.db_path)
        with self.assertRaises(MentorNotFoundError):
            cancel_booking(
                booking["booking_id"],
                profile_id=self.other_profile["profile_id"],
                db_path=self.db_path,
            )

    def test_meeting_link_validation_and_access_control(self):
        _, _, booking = self.confirmed_booking()
        with self.assertRaises(MentorValidationError):
            update_meeting_link(
                booking["booking_id"],
                booking["mentor_id"],
                "http://meet.example.com/room",
                db_path=self.db_path,
            )
        with self.assertRaises(MentorValidationError):
            update_meeting_link(
                booking["booking_id"],
                booking["mentor_id"],
                "javascript:alert(1)",
                db_path=self.db_path,
            )
        with self.assertRaises(MentorNotFoundError):
            update_meeting_link(
                booking["booking_id"],
                "wrong-mentor",
                "https://meet.example.com/room",
                db_path=self.db_path,
            )
        updated = update_meeting_link(
            booking["booking_id"],
            booking["mentor_id"],
            "https://meet.example.com/room-123",
            db_path=self.db_path,
        )
        self.assertEqual(updated["meeting_link"], "https://meet.example.com/room-123")
        public = get_public_mentor(booking["mentor_id"], db_path=self.db_path)
        self.assertNotIn("meeting_link", public)

    def test_reschedule_request_can_be_cleared_by_mentor(self):
        _, _, booking = self.confirmed_booking()
        requested = request_reschedule(
            booking["booking_id"],
            self.profile["profile_id"],
            "Please move the meeting one hour later.",
            db_path=self.db_path,
        )
        self.assertIsNotNone(requested["reschedule_requested_at"])
        cleared = clear_reschedule_request(
            booking["booking_id"], booking["mentor_id"], db_path=self.db_path
        )
        self.assertIsNone(cleared["reschedule_requested_at"])

    def test_completed_booking_feedback_and_duplicate_prevention(self):
        _, _, booking = self.confirmed_booking()
        with self.assertRaises(MentorConflictError):
            submit_feedback(
                booking["booking_id"],
                self.profile["profile_id"],
                5,
                "Useful session",
                True,
                "No extra support",
                db_path=self.db_path,
            )
        future = datetime.now(timezone.utc) + timedelta(days=7)
        with patch("core.mentor_store.utc_now", return_value=future):
            completed = complete_booking(
                booking["booking_id"],
                booking["mentor_id"],
                "Practise two STAR examples before the next interview.",
                db_path=self.db_path,
            )
        self.assertEqual(completed["status"], BOOKING_COMPLETED)
        self.assertIn("STAR", completed["mentor_recommendations"])
        feedback = submit_feedback(
            booking["booking_id"],
            self.profile["profile_id"],
            5,
            "Very helpful and practical.",
            True,
            "More mock interviews",
            db_path=self.db_path,
        )
        self.assertEqual(feedback["rating"], 5)
        self.assertTrue(feedback["helpful"])
        with self.assertRaises(MentorConflictError):
            submit_feedback(
                booking["booking_id"],
                self.profile["profile_id"],
                4,
                "Second attempt",
                True,
                "",
                db_path=self.db_path,
            )
        self.assertEqual(
            get_feedback(
                booking["booking_id"], self.profile["profile_id"], db_path=self.db_path
            )["rating"],
            5,
        )
        self.assertIsNone(
            get_feedback(
                booking["booking_id"],
                self.other_profile["profile_id"],
                db_path=self.db_path,
            )
        )

    def test_mentor_recommendations_require_completed_booking(self):
        _, _, booking = self.confirmed_booking()
        with self.assertRaises(MentorConflictError):
            update_mentor_recommendations(
                booking["booking_id"],
                booking["mentor_id"],
                "Review the job description.",
                db_path=self.db_path,
            )

    def test_profile_deletion_reopens_reserved_slot(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        slot = self.make_slot(mentor["mentor_id"])
        self.book(mentor["mentor_id"], slot["slot_id"])
        deleted = delete_profile_record(
            self.profile["profile_id"], db_path=self.db_path
        )
        self.assertTrue(deleted)
        open_ids = {
            item["slot_id"]
            for item in list_open_slots(mentor["mentor_id"], db_path=self.db_path)
        }
        self.assertIn(slot["slot_id"], open_ids)

    def test_booking_reference_is_unique_across_slots(self):
        result = self.approved_mentor()
        mentor = result["mentor"]
        first_slot = self.make_slot(mentor["mentor_id"], days=2, hour=9)
        second_slot = self.make_slot(mentor["mentor_id"], days=2, hour=11)
        first = self.book(mentor["mentor_id"], first_slot["slot_id"])
        second = self.book(mentor["mentor_id"], second_slot["slot_id"])
        self.assertNotEqual(first["booking_reference"], second["booking_reference"])
        self.assertEqual(
            len(list_bookings_for_profile(self.profile["profile_id"], db_path=self.db_path)),
            2,
        )
        self.assertEqual(
            len(list_bookings_for_mentor(mentor["mentor_id"], db_path=self.db_path)),
            2,
        )


class MentorAccessAndMigrationTests(MentorTestBase):
    def test_access_code_hash_round_trip(self):
        code = generate_access_code()
        encoded = hash_access_code(code)
        self.assertNotIn(code, encoded)
        self.assertTrue(verify_access_code(code, encoded))
        self.assertFalse(verify_access_code("wrong", encoded))
        self.assertFalse(verify_access_code(code, "not-a-hash"))

    def test_admin_access_configuration_and_verification(self):
        self.assertFalse(admin_access_configured({}))
        self.assertFalse(verify_admin_access("code", {}))
        self.assertTrue(admin_access_configured({"access_code": "strong-code"}))
        self.assertTrue(verify_admin_access("strong-code", {"access_code": "strong-code"}))
        self.assertFalse(verify_admin_access("wrong", {"access_code": "strong-code"}))
        encoded = hash_access_code("hashed-code")
        self.assertTrue(admin_access_configured({"access_code_hash": encoded}))
        self.assertTrue(
            verify_admin_access("hashed-code", {"access_code_hash": encoded})
        )
        self.assertFalse(
            verify_admin_access("wrong", {"access_code_hash": encoded})
        )

    def test_nairobi_timezone_conversion(self):
        local_day = datetime.now(timezone.utc).astimezone().date()
        converted = nairobi_to_utc(local_day, datetime.min.time().replace(hour=9))
        self.assertEqual(converted.utcoffset(), timedelta(0))
        formatted = format_nairobi(converted)
        self.assertIn("EAT", formatted)
        self.assertIn("09:00", formatted)

    def test_schema_creation_is_idempotent_and_preserves_existing_data(self):
        initialize_database(self.db_path)
        initialize_database(self.db_path)
        connection = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
            profile_count = connection.execute(
                "SELECT COUNT(*) FROM job_seekers"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertIn("mentor_applications", tables)
        self.assertIn("mentor_profiles", tables)
        self.assertIn("mentor_access", tables)
        self.assertIn("mentor_availability", tables)
        self.assertIn("mentor_bookings", tables)
        self.assertIn("mentor_feedback", tables)
        self.assertIn("idx_mentor_bookings_active_slot", indexes)
        self.assertIn("idx_mentor_pending_application_email", indexes)
        self.assertEqual(profile_count, 2)

    def test_public_mentor_does_not_expose_private_records(self):
        result = self.approved_mentor()
        mentor_id = result["mentor"]["mentor_id"]
        public = get_public_mentor(mentor_id, db_path=self.db_path)
        self.assertNotIn("application_id", public)
        self.assertNotIn("approval_status", public)
        self.assertNotIn("email", public)
        self.assertNotIn("access_code_hash", public)
        self.assertEqual(
            get_mentor_workspace(mentor_id, db_path=self.db_path)["mentor_id"],
            mentor_id,
        )
