"""Workspace export and deletion controls.

These functions operate on one owner only. They never delete the shared mentor
directory or another person's records. An approved mentor application is kept as
the public mentor directory entry, but its link to the job-seeker profile and its
private supporting information are removed.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .database import get_database_connection
from .workspace import (
    MENTOR_DIRECTORY_OWNER_ID,
    current_cv_dir,
    get_current_owner_id,
    normalize_owner_id,
)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _rows(connection: sqlite3.Connection, query: str, parameters=()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def _without_owner(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row.pop("owner_id", None)
    return rows


def _cv_files(owner_id: str) -> list[dict[str, Any]]:
    directory = current_cv_dir(owner_id)
    if not directory.exists():
        return []
    files = []
    for path in sorted(directory.glob("*.pdf")):
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(
                    timespec="seconds"
                ),
            }
        )
    return files


def export_owner_data(
    owner_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return one owner's personal data as a JSON-serialisable dictionary."""

    owner = normalize_owner_id(owner_id or get_current_owner_id())

    with get_database_connection(db_path) as connection:
        profiles = _without_owner(
            _rows(connection, "SELECT * FROM job_seekers WHERE owner_id = ? ORDER BY created_at", (owner,))
        )
        sessions = _without_owner(
            _rows(
                connection,
                """
                SELECT s.*
                FROM interview_sessions s
                JOIN job_seekers p ON p.profile_id = s.profile_id
                WHERE p.owner_id = ?
                ORDER BY s.created_at
                """,
                (owner,),
            )
        )
        responses = _without_owner(
            _rows(
                connection,
                """
                SELECT r.*
                FROM interview_responses r
                JOIN interview_sessions s ON s.id = r.session_id
                JOIN job_seekers p ON p.profile_id = s.profile_id
                WHERE p.owner_id = ?
                ORDER BY r.created_at
                """,
                (owner,),
            )
        )
        custom_questions = _without_owner(
            _rows(
                connection,
                """
                SELECT q.*
                FROM interview_custom_questions q
                JOIN interview_sessions s ON s.id = q.session_id
                JOIN job_seekers p ON p.profile_id = s.profile_id
                WHERE p.owner_id = ?
                ORDER BY q.created_at
                """,
                (owner,),
            )
        )
        assessments = _without_owner(
            _rows(
                connection,
                """
                SELECT a.*
                FROM skill_assessments a
                JOIN job_seekers p ON p.profile_id = a.profile_id
                WHERE p.owner_id = ?
                ORDER BY a.created_at
                """,
                (owner,),
            )
        )
        assessment_responses = _without_owner(
            _rows(
                connection,
                """
                SELECT r.*
                FROM skill_assessment_responses r
                JOIN skill_assessments a ON a.assessment_id = r.assessment_id
                JOIN job_seekers p ON p.profile_id = a.profile_id
                WHERE p.owner_id = ?
                ORDER BY r.created_at
                """,
                (owner,),
            )
        )
        applications = _without_owner(
            _rows(
                connection,
                "SELECT * FROM mentor_applications WHERE owner_id = ? ORDER BY created_at",
                (owner,),
            )
        )
        bookings = _without_owner(
            _rows(
                connection,
                """
                SELECT b.*
                FROM mentor_bookings b
                JOIN job_seekers p ON p.profile_id = b.profile_id
                WHERE p.owner_id = ?
                ORDER BY b.created_at
                """,
                (owner,),
            )
        )
        feedback = _without_owner(
            _rows(
                connection,
                """
                SELECT f.*
                FROM mentor_feedback f
                JOIN mentor_bookings b ON b.booking_id = f.booking_id
                JOIN job_seekers p ON p.profile_id = b.profile_id
                WHERE p.owner_id = ?
                ORDER BY f.created_at
                """,
                (owner,),
            )
        )
        draft_rows = _without_owner(
            _rows(
                connection,
                "SELECT * FROM cv_drafts WHERE owner_id = ? ORDER BY updated_at",
                (owner,),
            )
        )

    drafts = []
    for row in draft_rows:
        try:
            content = json.loads(row.get("draft_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            content = {}
        row.pop("draft_json", None)
        drafts.append(
            {
                "profile_id": row.get("profile_id"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "draft": content,
            }
        )

    return {
        "format_version": 1,
        "exported_at": _now(),
        "workspace_scope": "signed-in account" if owner != "local" else "local workspace",
        "profiles": profiles,
        "interview_sessions": sessions,
        "interview_responses": responses,
        "interview_custom_questions": custom_questions,
        "skill_assessments": assessments,
        "skill_assessment_responses": assessment_responses,
        "mentor_applications": applications,
        "mentor_bookings": bookings,
        "mentor_feedback": feedback,
        "cv_drafts": drafts,
        "cv_files": _cv_files(owner),
    }


def _delete_cv_files(owner: str) -> int:
    directory = current_cv_dir(owner)
    if not directory.exists():
        return 0

    if owner == "local":
        removed = 0
        for path in directory.iterdir():
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    continue
                removed += 1
        return removed

    removed = sum(1 for path in directory.rglob("*") if path.is_file())
    shutil.rmtree(directory, ignore_errors=True)
    return removed


def delete_owner_data(
    owner_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Delete one owner's personal data and generated CV files.

    Returns counts so the interface can confirm what was removed. The shared
    mentor directory and other people's records are left untouched.
    """

    owner = normalize_owner_id(owner_id or get_current_owner_id())
    now = _now()

    with get_database_connection(db_path) as connection:
        profiles = connection.execute(
            "SELECT COUNT(*) FROM job_seekers WHERE owner_id = ?", (owner,)
        ).fetchone()[0]
        sessions = connection.execute(
            """
            SELECT COUNT(*)
            FROM interview_sessions s
            JOIN job_seekers p ON p.profile_id = s.profile_id
            WHERE p.owner_id = ?
            """,
            (owner,),
        ).fetchone()[0]
        responses = connection.execute(
            """
            SELECT COUNT(*)
            FROM interview_responses r
            JOIN interview_sessions s ON s.id = r.session_id
            JOIN job_seekers p ON p.profile_id = s.profile_id
            WHERE p.owner_id = ?
            """,
            (owner,),
        ).fetchone()[0]
        assessments = connection.execute(
            """
            SELECT COUNT(*)
            FROM skill_assessments a
            JOIN job_seekers p ON p.profile_id = a.profile_id
            WHERE p.owner_id = ?
            """,
            (owner,),
        ).fetchone()[0]
        assessment_responses = connection.execute(
            """
            SELECT COUNT(*)
            FROM skill_assessment_responses r
            JOIN skill_assessments a ON a.assessment_id = r.assessment_id
            JOIN job_seekers p ON p.profile_id = a.profile_id
            WHERE p.owner_id = ?
            """,
            (owner,),
        ).fetchone()[0]
        bookings = connection.execute(
            """
            SELECT COUNT(*)
            FROM mentor_bookings b
            JOIN job_seekers p ON p.profile_id = b.profile_id
            WHERE p.owner_id = ?
            """,
            (owner,),
        ).fetchone()[0]
        feedback = connection.execute(
            """
            SELECT COUNT(*)
            FROM mentor_feedback f
            JOIN mentor_bookings b ON b.booking_id = f.booking_id
            JOIN job_seekers p ON p.profile_id = b.profile_id
            WHERE p.owner_id = ?
            """,
            (owner,),
        ).fetchone()[0]
        drafts = connection.execute(
            "SELECT COUNT(*) FROM cv_drafts WHERE owner_id = ?", (owner,)
        ).fetchone()[0]

        approved_applications = connection.execute(
            """
            SELECT a.application_id
            FROM mentor_applications a
            JOIN mentor_profiles m ON m.application_id = a.application_id
            WHERE a.owner_id = ?
            """,
            (owner,),
        ).fetchall()
        approved_ids = [row["application_id"] for row in approved_applications]

        for application_id in approved_ids:
            connection.execute(
                """
                UPDATE mentor_applications
                SET applicant_profile_id = NULL,
                    email = ?,
                    supporting_info = '',
                    avatar_url = '',
                    review_note = NULL,
                    owner_id = ?,
                    updated_at = ?
                WHERE application_id = ?
                """,
                (
                    f"deleted+{uuid4().hex}@example.invalid",
                    MENTOR_DIRECTORY_OWNER_ID,
                    now,
                    application_id,
                ),
            )

        if approved_ids:
            placeholders = ",".join("?" for _ in approved_ids)
            cursor = connection.execute(
                f"""
                DELETE FROM mentor_applications
                WHERE owner_id = ?
                  AND application_id NOT IN ({placeholders})
                """,
                (owner, *approved_ids),
            )
        else:
            cursor = connection.execute(
                "DELETE FROM mentor_applications WHERE owner_id = ?", (owner,)
            )
        applications = cursor.rowcount

        # Deleting the profiles cascades to sessions, assessments, bookings and
        # feedback. Approved applications were detached above.
        connection.execute("DELETE FROM job_seekers WHERE owner_id = ?", (owner,))
        connection.execute("DELETE FROM cv_drafts WHERE owner_id = ?", (owner,))

    cv_files = _delete_cv_files(owner)

    return {
        "deleted_at": now,
        "profiles": profiles,
        "interview_sessions": sessions,
        "interview_responses": responses,
        "skill_assessments": assessments,
        "skill_assessment_responses": assessment_responses,
        "mentor_applications": applications,
        "mentor_bookings": bookings,
        "mentor_feedback": feedback,
        "cv_drafts": drafts,
        "cv_files": cv_files,
        "kept_mentor_directory_entries": len(approved_ids),
    }


__all__ = ["delete_owner_data", "export_owner_data"]
