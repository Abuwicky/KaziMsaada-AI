"""Database connection and schema management for KaziMsaada AI.

This module is the single source of truth for the SQLite database used by
both the command-line application and the Streamlit interface.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from .config import DATABASE_FILE, PROFILE_FILE

MIGRATION_NAME = "json_profiles_to_sqlite_v1"


@contextmanager
def get_database_connection(
    db_path: str | Path | None = None,
) -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on failure, and close.

    ``sqlite3.Error`` exceptions are intentionally allowed to propagate so the
    caller can present a friendly message while keeping details available for
    debugging.
    """

    path = Path(db_path) if db_path is not None else DATABASE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(db_path: str | Path | None = None) -> None:
    """Create the required tables if they do not already exist."""

    with get_database_connection(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS job_seekers (
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
            CREATE TABLE IF NOT EXISTS migration_history (
                migration_name TEXT PRIMARY KEY,
                completed_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS interview_sessions (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                target_role TEXT NOT NULL,
                category TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'in_progress'
                    CHECK (status IN ('in_progress', 'completed', 'cancelled')),
                question_ids TEXT NOT NULL DEFAULT '[]',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                overall_feedback TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (profile_id)
                    REFERENCES job_seekers(profile_id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS interview_responses (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                question_text TEXT NOT NULL,
                question_order INTEGER NOT NULL DEFAULT 0,
                answer_text TEXT NOT NULL,
                feedback TEXT NOT NULL DEFAULT '{}',
                assessment_data TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id)
                    REFERENCES interview_sessions(id)
                    ON DELETE CASCADE,
                UNIQUE (session_id, question_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS interview_custom_questions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                question_text TEXT NOT NULL,
                category TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                assesses TEXT NOT NULL DEFAULT '',
                structure TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'ai',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id)
                    REFERENCES interview_sessions(id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_interview_sessions_profile_started
            ON interview_sessions(profile_id, started_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_interview_sessions_status
            ON interview_sessions(profile_id, status)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_interview_responses_session_order
            ON interview_responses(session_id, question_order)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_interview_custom_questions_session
            ON interview_custom_questions(session_id, created_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_assessments (
                assessment_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                assessment_name TEXT NOT NULL,
                assessment_type TEXT NOT NULL
                    CHECK (assessment_type IN ('knowledge', 'practical', 'combined')),
                assessment_key TEXT NOT NULL,
                target_type TEXT NOT NULL
                    CHECK (target_type IN ('career_area', 'skill')),
                target_id TEXT NOT NULL,
                skill_category TEXT NOT NULL,
                content_version TEXT NOT NULL,
                question_ids TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'in_progress'
                    CHECK (status IN ('in_progress', 'completed')),
                score REAL
                    CHECK (score IS NULL OR (score >= 0 AND score <= 100)),
                proficiency_level TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (profile_id)
                    REFERENCES job_seekers(profile_id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_assessment_responses (
                response_id TEXT PRIMARY KEY,
                assessment_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                question_text TEXT NOT NULL,
                question_type TEXT NOT NULL
                    CHECK (question_type IN ('knowledge', 'practical')),
                question_order INTEGER NOT NULL DEFAULT 0,
                response_text TEXT NOT NULL DEFAULT '',
                selected_answer TEXT,
                is_correct INTEGER
                    CHECK (is_correct IS NULL OR is_correct IN (0, 1)),
                score_awarded REAL,
                feedback TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (assessment_id)
                    REFERENCES skill_assessments(assessment_id)
                    ON DELETE CASCADE,
                UNIQUE (assessment_id, question_id)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_skill_assessments_profile_started
            ON skill_assessments(profile_id, started_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_skill_assessments_profile_status
            ON skill_assessments(profile_id, status)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_skill_assessments_target
            ON skill_assessments(
                profile_id,
                assessment_key,
                assessment_type,
                content_version
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_skill_assessment_responses_order
            ON skill_assessment_responses(assessment_id, question_order)
            """
        )

        # Mentor Meeting Centre. These tables are additive: existing profiles,
        # CVs, interview sessions and assessments are never rewritten.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mentor_applications (
                application_id TEXT PRIMARY KEY,
                applicant_profile_id TEXT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                professional_title TEXT NOT NULL,
                industry TEXT NOT NULL,
                specialisation TEXT NOT NULL DEFAULT '',
                areas_of_expertise TEXT NOT NULL DEFAULT '[]',
                experience TEXT NOT NULL,
                biography TEXT NOT NULL,
                qualifications TEXT NOT NULL,
                languages TEXT NOT NULL DEFAULT '[]',
                supporting_info TEXT NOT NULL DEFAULT '',
                avatar_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected')),
                review_note TEXT,
                reviewed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (applicant_profile_id)
                    REFERENCES job_seekers(profile_id)
                    ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mentor_profiles (
                mentor_id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                professional_title TEXT NOT NULL,
                biography TEXT NOT NULL,
                industry TEXT NOT NULL,
                specialisation TEXT NOT NULL,
                experience TEXT NOT NULL,
                qualifications TEXT NOT NULL,
                languages TEXT NOT NULL DEFAULT '[]',
                coaching_areas TEXT NOT NULL DEFAULT '[]',
                duration_options TEXT NOT NULL DEFAULT '[30, 45, 60]',
                avatar_url TEXT NOT NULL DEFAULT '',
                approval_status TEXT NOT NULL DEFAULT 'approved'
                    CHECK (approval_status IN ('approved', 'suspended')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (application_id)
                    REFERENCES mentor_applications(application_id)
                    ON DELETE RESTRICT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mentor_access (
                mentor_id TEXT PRIMARY KEY,
                access_code_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                rotated_at TEXT,
                FOREIGN KEY (mentor_id)
                    REFERENCES mentor_profiles(mentor_id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mentor_availability (
                slot_id TEXT PRIMARY KEY,
                mentor_id TEXT NOT NULL,
                start_at_utc TEXT NOT NULL,
                end_at_utc TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL
                    CHECK (duration_minutes IN (30, 45, 60, 90)),
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'booked', 'removed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (mentor_id)
                    REFERENCES mentor_profiles(mentor_id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mentor_bookings (
                booking_id TEXT PRIMARY KEY,
                booking_reference TEXT NOT NULL UNIQUE,
                profile_id TEXT NOT NULL,
                mentor_id TEXT NOT NULL,
                availability_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending',
                        'confirmed',
                        'rejected',
                        'cancelled',
                        'completed'
                    )),
                purpose TEXT NOT NULL,
                target_job_role TEXT NOT NULL DEFAULT '',
                scheduled_start_utc TEXT NOT NULL,
                scheduled_end_utc TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL
                    CHECK (duration_minutes IN (30, 45, 60, 90)),
                meeting_link TEXT,
                mentor_recommendations TEXT NOT NULL DEFAULT '',
                reschedule_requested_at TEXT,
                reschedule_note TEXT,
                cancellation_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                confirmed_at TEXT,
                cancelled_at TEXT,
                completed_at TEXT,
                FOREIGN KEY (profile_id)
                    REFERENCES job_seekers(profile_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (mentor_id)
                    REFERENCES mentor_profiles(mentor_id)
                    ON DELETE RESTRICT,
                FOREIGN KEY (availability_id)
                    REFERENCES mentor_availability(slot_id)
                    ON DELETE RESTRICT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mentor_feedback (
                feedback_id TEXT PRIMARY KEY,
                booking_id TEXT NOT NULL UNIQUE,
                profile_id TEXT NOT NULL,
                mentor_id TEXT NOT NULL,
                rating INTEGER NOT NULL
                    CHECK (rating BETWEEN 1 AND 5),
                comment TEXT NOT NULL DEFAULT '',
                helpful INTEGER NOT NULL DEFAULT 1
                    CHECK (helpful IN (0, 1)),
                further_support TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (booking_id)
                    REFERENCES mentor_bookings(booking_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (profile_id)
                    REFERENCES job_seekers(profile_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (mentor_id)
                    REFERENCES mentor_profiles(mentor_id)
                    ON DELETE RESTRICT
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mentor_pending_application_email
            ON mentor_applications(lower(email))
            WHERE status = 'pending'
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mentor_applications_status_created
            ON mentor_applications(status, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mentor_applications_profile
            ON mentor_applications(applicant_profile_id, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mentor_profiles_public
            ON mentor_profiles(approval_status, industry, full_name)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mentor_availability_mentor_start
            ON mentor_availability(mentor_id, start_at_utc)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mentor_availability_unique_start
            ON mentor_availability(mentor_id, start_at_utc)
            WHERE status != 'removed'
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mentor_bookings_profile_created
            ON mentor_bookings(profile_id, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mentor_bookings_mentor_created
            ON mentor_bookings(mentor_id, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mentor_bookings_status_start
            ON mentor_bookings(mentor_id, status, scheduled_start_utc)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mentor_bookings_active_slot
            ON mentor_bookings(availability_id)
            WHERE status IN ('pending', 'confirmed')
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mentor_feedback_mentor
            ON mentor_feedback(mentor_id, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_mentor_booking_delete_reopen_slot
            AFTER DELETE ON mentor_bookings
            BEGIN
                UPDATE mentor_availability
                SET status = 'open'
                WHERE slot_id = OLD.availability_id
                  AND status = 'booked'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM mentor_bookings
                      WHERE availability_id = OLD.availability_id
                        AND status IN ('pending', 'confirmed')
                  );
            END
            """
        )


def migrate_json_profiles(
    profile_file: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict:
    """Import legacy JSON profiles into SQLite exactly once.

    The original JSON file is never modified or deleted. The migration is
    recorded in ``migration_history`` inside the same transaction.

    Returns a result dictionary describing what happened. Database errors and
    unreadable source files are reported through ``status``/``error`` instead
    of being raised, so both interfaces can decide how to surface them.
    """

    source = Path(profile_file) if profile_file is not None else PROFILE_FILE

    if not source.exists():
        return {
            "status": "no_source",
            "imported": 0,
            "error": None,
        }

    try:
        with source.open("r", encoding="utf-8") as file:
            profiles = json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        return {
            "status": "source_error",
            "imported": 0,
            "error": str(error),
        }

    if not isinstance(profiles, list):
        return {
            "status": "invalid_source",
            "imported": 0,
            "error": None,
        }

    try:
        with get_database_connection(db_path) as connection:
            existing = connection.execute(
                """
                SELECT migration_name
                FROM migration_history
                WHERE migration_name = ?
                """,
                (MIGRATION_NAME,),
            ).fetchone()

            if existing:
                return {
                    "status": "already_completed",
                    "imported": 0,
                    "error": None,
                }

            imported_count = 0

            for profile in profiles:
                if not isinstance(profile, dict):
                    continue

                profile_id = profile.get("profile_id") or str(uuid4())

                skills = profile.get("skills", [])
                if not isinstance(skills, list):
                    skills = []

                skills = [
                    str(skill).strip()
                    for skill in skills
                    if str(skill).strip()
                ]

                created_at = profile.get("created_at")
                if not created_at:
                    created_at = datetime.now().astimezone().isoformat(
                        timespec="seconds"
                    )

                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO job_seekers (
                        profile_id,
                        name,
                        education,
                        location,
                        experience,
                        career_interest,
                        skills,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(profile_id),
                        str(profile.get("name", "Not provided")),
                        str(profile.get("education", "Not provided")),
                        str(profile.get("location", "Not provided")),
                        str(profile.get("experience", "Not provided")),
                        str(profile.get("career_interest", "Not provided")),
                        json.dumps(skills, ensure_ascii=False),
                        str(created_at),
                        profile.get("updated_at"),
                    ),
                )

                imported_count += cursor.rowcount

            connection.execute(
                """
                INSERT INTO migration_history (
                    migration_name,
                    completed_at
                )
                VALUES (?, ?)
                """,
                (
                    MIGRATION_NAME,
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                ),
            )

        return {
            "status": "imported",
            "imported": imported_count,
            "error": None,
        }

    except sqlite3.Error as error:
        return {
            "status": "database_error",
            "imported": 0,
            "error": str(error),
        }
