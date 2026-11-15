"""Persistence for Mock Interview Centre sessions and responses.

All data stays in the existing KaziMsaada AI SQLite database. Every operation
accepts an optional ``db_path`` so tests can use isolated temporary databases.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .database import get_database_connection
from .interview import (
    CATEGORY_LOOKUP,
    DIFFICULTY_IDS,
    MAX_ANSWER_CHARS,
    MAX_QUESTIONS_PER_SESSION,
    MAX_TARGET_ROLE_CHARS,
    get_question,
)

SESSION_IN_PROGRESS = "in_progress"
SESSION_COMPLETED = "completed"
SESSION_CANCELLED = "cancelled"
SESSION_STATUSES = (SESSION_IN_PROGRESS, SESSION_COMPLETED, SESSION_CANCELLED)


class InterviewStoreError(Exception):
    """Base class for interview storage failures."""


class InterviewValidationError(InterviewStoreError, ValueError):
    """Raised when interview input fails validation."""


class InterviewSessionNotFound(InterviewStoreError, LookupError):
    """Raised when a session does not exist or is not owned by the profile."""


class InterviewSessionClosed(InterviewStoreError):
    """Raised when an action is attempted on a completed or cancelled session."""


class DuplicateResponseError(InterviewStoreError):
    """Raised when a question has already been answered in a session."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _json_load(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError, ValueError):
        return default
    return parsed


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _session_from_row(row: sqlite3.Row) -> dict[str, Any]:
    session = dict(row)
    session["question_ids"] = _json_load(session.get("question_ids"), [])
    if not isinstance(session["question_ids"], list):
        session["question_ids"] = []
    session["overall_feedback"] = _json_load(
        session.get("overall_feedback"), None
    )
    session["answered_count"] = int(session.get("answered_count") or 0)
    return session


def _response_from_row(row: sqlite3.Row) -> dict[str, Any]:
    response = dict(row)
    response["feedback"] = _json_load(response.get("feedback"), {})
    response["assessment_data"] = _json_load(response.get("assessment_data"), {})
    return response


def _clean_text(value: Any, field_name: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise InterviewValidationError(f"{field_name} is required.")
    if len(text) > maximum:
        raise InterviewValidationError(
            f"{field_name} must be {maximum} characters or fewer."
        )
    return text


def _validate_profile(connection: sqlite3.Connection, profile_id: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM job_seekers WHERE profile_id = ?",
        (profile_id,),
    ).fetchone()
    if row is None:
        raise InterviewValidationError("The active profile could not be found.")


def _get_owned_session_row(
    connection: sqlite3.Connection,
    session_id: str,
    profile_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT *
        FROM interview_sessions
        WHERE id = ? AND profile_id = ?
        """,
        (session_id, profile_id),
    ).fetchone()
    if row is None:
        raise InterviewSessionNotFound("That practice session could not be found.")
    return row


def create_session(
    profile_id: str,
    target_role: str,
    category: str,
    difficulty: str,
    question_ids: list[str] | tuple[str, ...],
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create an incomplete practice session and return it."""

    profile_id = _clean_text(profile_id, "Profile", 80)
    target_role = _clean_text(target_role, "Target job position", MAX_TARGET_ROLE_CHARS)
    category = _clean_text(category, "Interview category", 80)
    difficulty = _clean_text(difficulty, "Difficulty", 40)

    if category not in CATEGORY_LOOKUP:
        raise InterviewValidationError("Choose a valid interview category.")
    if difficulty not in DIFFICULTY_IDS:
        raise InterviewValidationError("Choose a valid difficulty level.")

    if isinstance(question_ids, str):
        question_ids = [question_ids]
    if not isinstance(question_ids, (list, tuple)):
        raise InterviewValidationError("At least one question is required.")

    cleaned_ids: list[str] = []
    for question_id in question_ids:
        text = str(question_id or "").strip()
        if not text:
            continue
        if get_question(text) is None:
            raise InterviewValidationError("An unknown interview question was selected.")
        if text not in cleaned_ids:
            cleaned_ids.append(text)

    if not cleaned_ids:
        raise InterviewValidationError("At least one question is required.")
    if len(cleaned_ids) > MAX_QUESTIONS_PER_SESSION:
        raise InterviewValidationError(
            f"Choose no more than {MAX_QUESTIONS_PER_SESSION} questions."
        )

    now = _now()
    session_id = str(uuid4())

    with get_database_connection(db_path) as connection:
        _validate_profile(connection, profile_id)
        connection.execute(
            """
            INSERT INTO interview_sessions (
                id,
                profile_id,
                target_role,
                category,
                difficulty,
                status,
                question_ids,
                started_at,
                completed_at,
                overall_feedback,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                profile_id,
                target_role,
                category,
                difficulty,
                SESSION_IN_PROGRESS,
                _json_dump(cleaned_ids),
                now,
                None,
                None,
                now,
                now,
            ),
        )

    session = get_session(session_id, profile_id, db_path=db_path)
    if session is None:
        raise InterviewStoreError("The practice session could not be loaded after saving.")
    return session


def get_session(
    session_id: str,
    profile_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return one session only when it belongs to the profile."""

    with get_database_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                s.*,
                (
                    SELECT COUNT(*)
                    FROM interview_responses r
                    WHERE r.session_id = s.id
                ) AS answered_count
            FROM interview_sessions s
            WHERE s.id = ? AND s.profile_id = ?
            """,
            (session_id, profile_id),
        ).fetchone()

    return _session_from_row(row) if row else None


def list_sessions(
    profile_id: str,
    status: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return this profile's sessions, newest first."""

    if status is not None and status not in SESSION_STATUSES:
        raise InterviewValidationError("Unknown interview session status.")

    query = """
        SELECT
            s.*,
            (
                SELECT COUNT(*)
                FROM interview_responses r
                WHERE r.session_id = s.id
            ) AS answered_count
        FROM interview_sessions s
        WHERE s.profile_id = ?
    """
    params: list[Any] = [profile_id]
    if status is not None:
        query += " AND s.status = ?"
        params.append(status)
    query += " ORDER BY s.started_at DESC, s.created_at DESC"

    with get_database_connection(db_path) as connection:
        rows = connection.execute(query, tuple(params)).fetchall()

    return [_session_from_row(row) for row in rows]


def _response_count(
    connection: sqlite3.Connection,
    session_id: str,
) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS total FROM interview_responses WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return int(row["total"] if row else 0)


def save_response(
    session_id: str,
    profile_id: str,
    question_id: str,
    answer_text: str,
    feedback: Mapping[str, Any],
    assessment_data: Mapping[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Save one answer, rejecting empty or duplicate submissions."""

    answer_text = _clean_text(answer_text, "Answer", MAX_ANSWER_CHARS)
    if len(answer_text.split()) < 3:
        raise InterviewValidationError(
            "Write a slightly fuller answer before submitting."
        )
    if not isinstance(feedback, Mapping):
        raise InterviewValidationError("Feedback data is required.")

    question = get_question(question_id)
    if question is None:
        raise InterviewValidationError("An unknown interview question was submitted.")
    if assessment_data is not None and not isinstance(assessment_data, Mapping):
        raise InterviewValidationError("Assessment data must be an object.")

    response_id = str(uuid4())
    now = _now()

    try:
        with get_database_connection(db_path) as connection:
            session_row = _get_owned_session_row(connection, session_id, profile_id)
            if session_row["status"] != SESSION_IN_PROGRESS:
                raise InterviewSessionClosed(
                    "This practice session is no longer accepting answers."
                )

            question_ids = _json_load(session_row["question_ids"], [])
            if question_id not in question_ids:
                raise InterviewValidationError(
                    "That question is not part of this practice session."
                )

            duplicate = connection.execute(
                """
                SELECT 1
                FROM interview_responses
                WHERE session_id = ? AND question_id = ?
                """,
                (session_id, question_id),
            ).fetchone()
            if duplicate:
                raise DuplicateResponseError(
                    "This question has already been answered in this session."
                )

            question_order = question_ids.index(question_id)
            connection.execute(
                """
                INSERT INTO interview_responses (
                    id,
                    session_id,
                    question_id,
                    question_text,
                    question_order,
                    answer_text,
                    feedback,
                    assessment_data,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response_id,
                    session_id,
                    question_id,
                    question.question,
                    question_order,
                    answer_text,
                    _json_dump(dict(feedback)),
                    _json_dump(dict(assessment_data or {})),
                    now,
                ),
            )
    except sqlite3.IntegrityError as error:
        raise DuplicateResponseError(
            "This question has already been answered in this session."
        ) from error

    saved = get_response(session_id, profile_id, question_id, db_path=db_path)
    if saved is None:
        raise InterviewStoreError("The answer could not be loaded after saving.")
    return saved


def get_response(
    session_id: str,
    profile_id: str,
    question_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    with get_database_connection(db_path) as connection:
        _get_owned_session_row(connection, session_id, profile_id)
        row = connection.execute(
            """
            SELECT *
            FROM interview_responses
            WHERE session_id = ? AND question_id = ?
            """,
            (session_id, question_id),
        ).fetchone()
    return _response_from_row(row) if row else None


def get_responses(
    session_id: str,
    profile_id: str,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return this profile's responses in interview order."""

    with get_database_connection(db_path) as connection:
        _get_owned_session_row(connection, session_id, profile_id)
        rows = connection.execute(
            """
            SELECT *
            FROM interview_responses
            WHERE session_id = ?
            ORDER BY question_order, created_at
            """,
            (session_id,),
        ).fetchall()

    return [_response_from_row(row) for row in rows]


def complete_session(
    session_id: str,
    profile_id: str,
    overall_feedback: Mapping[str, Any],
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Mark a fully answered session as completed."""

    if not isinstance(overall_feedback, Mapping):
        raise InterviewValidationError("Overall feedback is required.")

    with get_database_connection(db_path) as connection:
        session_row = _get_owned_session_row(connection, session_id, profile_id)
        if session_row["status"] == SESSION_CANCELLED:
            raise InterviewSessionClosed(
                "A cancelled practice session cannot be completed."
            )
        if session_row["status"] != SESSION_COMPLETED:
            question_ids = _json_load(session_row["question_ids"], [])
            answered = _response_count(connection, session_id)
            if answered < len(question_ids):
                raise InterviewValidationError(
                    "Answer every question before completing the practice session."
                )

            now = _now()
            connection.execute(
                """
                UPDATE interview_sessions
                SET
                    status = ?,
                    completed_at = ?,
                    overall_feedback = ?,
                    updated_at = ?
                WHERE id = ? AND profile_id = ?
                """,
                (
                    SESSION_COMPLETED,
                    now,
                    _json_dump(dict(overall_feedback)),
                    now,
                    session_id,
                    profile_id,
                ),
            )

    session = get_session(session_id, profile_id, db_path=db_path)
    if session is None:
        raise InterviewSessionNotFound("That practice session could not be found.")
    return session


def cancel_session(
    session_id: str,
    profile_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """End an incomplete session without deleting its saved answers."""

    with get_database_connection(db_path) as connection:
        session_row = _get_owned_session_row(connection, session_id, profile_id)
        if session_row["status"] == SESSION_COMPLETED:
            raise InterviewSessionClosed("A completed practice session cannot be cancelled.")
        if session_row["status"] != SESSION_CANCELLED:
            connection.execute(
                """
                UPDATE interview_sessions
                SET status = ?, updated_at = ?
                WHERE id = ? AND profile_id = ?
                """,
                (SESSION_CANCELLED, _now(), session_id, profile_id),
            )

    session = get_session(session_id, profile_id, db_path=db_path)
    if session is None:
        raise InterviewSessionNotFound("That practice session could not be found.")
    return session


def delete_session(
    session_id: str,
    profile_id: str,
    db_path: str | Path | None = None,
) -> bool:
    """Delete a profile's session and its responses."""

    with get_database_connection(db_path) as connection:
        _get_owned_session_row(connection, session_id, profile_id)
        cursor = connection.execute(
            """
            DELETE FROM interview_sessions
            WHERE id = ? AND profile_id = ?
            """,
            (session_id, profile_id),
        )
    return cursor.rowcount == 1
