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
