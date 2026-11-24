"""SQLite persistence for guided skill assessments.

The store uses the existing KaziMsaada AI database and follows the same
connection and foreign-key conventions as the interview store. All functions
accept an optional ``db_path`` so tests never open the live database.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .database import get_database_connection
from .workspace import get_current_owner_id, normalize_owner_id
from .skill_assessment import (
    KNOWLEDGE,
    PRACTICAL,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUSES,
    AssessmentPlan,
    SkillAssessmentError,
    SkillAssessmentValidationError,
    evaluate_practical_response,
    get_question,
    proficiency_band,
    score_knowledge_question,
    score_to_percentage,
)


class SkillAssessmentNotFound(SkillAssessmentError, LookupError):
    """Raised when an assessment does not exist or is not owned by the profile."""


class DuplicateAssessmentResponse(SkillAssessmentError):
    """Raised when a question has already been submitted for an assessment."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


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


def _assessment_from_row(row: sqlite3.Row) -> dict[str, Any]:
    assessment = dict(row)
    assessment["question_ids"] = _json_load(
        assessment.get("question_ids"), []
    )
    if not isinstance(assessment["question_ids"], list):
        assessment["question_ids"] = []
    assessment["response_count"] = int(
        assessment.get("response_count") or 0
    )
    if assessment.get("score") is not None:
        assessment["score"] = float(assessment["score"])
    return assessment


def _response_from_row(row: sqlite3.Row) -> dict[str, Any]:
    response = dict(row)
    response["feedback"] = _json_load(response.get("feedback"), {})
    if not isinstance(response["feedback"], dict):
        response["feedback"] = {}
    if response.get("is_correct") is not None:
        response["is_correct"] = bool(response["is_correct"])
    if response.get("score_awarded") is not None:
        response["score_awarded"] = float(response["score_awarded"])
    return response


def _clean_text(value: Any, name: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise SkillAssessmentValidationError(f"{name} is required.")
    if len(text) > maximum:
        raise SkillAssessmentValidationError(
            f"{name} must be {maximum} characters or fewer."
        )
    return text


def _validate_profile(
    connection: sqlite3.Connection,
    profile_id: str,
) -> None:
    row = connection.execute(
        "SELECT 1 FROM job_seekers WHERE profile_id = ? AND owner_id = ?",
        (profile_id, normalize_owner_id(get_current_owner_id())),
    ).fetchone()
    if row is None:
        raise SkillAssessmentValidationError(
            "The active profile could not be found."
        )


def _get_owned_assessment_row(
    connection: sqlite3.Connection,
    assessment_id: str,
    profile_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT a.*
        FROM skill_assessments a
        JOIN job_seekers p ON p.profile_id = a.profile_id
        WHERE a.assessment_id = ? AND a.profile_id = ? AND p.owner_id = ?
        """,
        (assessment_id, profile_id, normalize_owner_id(get_current_owner_id())),
    ).fetchone()
    if row is None:
        raise SkillAssessmentNotFound(
            "That skill assessment could not be found for this profile."
        )
    return row


def create_assessment(
    profile_id: str,
    plan: AssessmentPlan,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a new in-progress attempt for the active profile."""

    profile_id = _clean_text(profile_id, "Profile", 80)
    if not isinstance(plan, AssessmentPlan):
        raise SkillAssessmentValidationError(
            "A valid assessment plan is required."
        )
    if not plan.questions:
        raise SkillAssessmentValidationError(
            "At least one assessment question is required."
        )

    assessment_id = str(uuid4())
    now = _now()
    question_ids = [question.question_id for question in plan.questions]

    with get_database_connection(db_path) as connection:
        _validate_profile(connection, profile_id)
        connection.execute(
            """
            INSERT INTO skill_assessments (
                assessment_id,
                profile_id,
                assessment_name,
                assessment_type,
                assessment_key,
                target_type,
                target_id,
                skill_category,
                content_version,
                question_ids,
                status,
                score,
                proficiency_level,
                started_at,
                completed_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment_id,
                profile_id,
                plan.assessment_name,
                plan.assessment_type,
                plan.assessment_key,
                plan.target_type,
                plan.target_id,
                plan.category,
                plan.content_version,
                _json_dump(question_ids),
                STATUS_IN_PROGRESS,
                None,
                None,
                now,
                None,
                now,
                now,
            ),
        )

    assessment = get_assessment(assessment_id, profile_id, db_path=db_path)
    if assessment is None:
        raise SkillAssessmentError(
            "The skill assessment could not be loaded after saving."
        )
    return assessment


def get_assessment(
    assessment_id: str,
    profile_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return one assessment only when it belongs to the profile."""

    with get_database_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                a.*,
                (
                    SELECT COUNT(*)
                    FROM skill_assessment_responses r
                    WHERE r.assessment_id = a.assessment_id
                ) AS response_count
            FROM skill_assessments a
            JOIN job_seekers p ON p.profile_id = a.profile_id
            WHERE a.assessment_id = ? AND a.profile_id = ? AND p.owner_id = ?
            """,
            (
                assessment_id,
                profile_id,
                normalize_owner_id(get_current_owner_id()),
            ),
        ).fetchone()

    return _assessment_from_row(row) if row else None


def list_assessments(
    profile_id: str,
    status: str | None = None,
    assessment_key: str | None = None,
    assessment_type: str | None = None,
    content_version: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return this profile's assessments, newest first."""

    if status is not None and status not in STATUSES:
        raise SkillAssessmentValidationError(
            "Unknown skill-assessment status."
        )

    query = """
        SELECT
            a.*,
            (
                SELECT COUNT(*)
                FROM skill_assessment_responses r
                WHERE r.assessment_id = a.assessment_id
            ) AS response_count
        FROM skill_assessments a
        JOIN job_seekers p ON p.profile_id = a.profile_id
        WHERE a.profile_id = ? AND p.owner_id = ?
    """
    params: list[Any] = [
        profile_id,
        normalize_owner_id(get_current_owner_id()),
    ]

    if status is not None:
        query += " AND a.status = ?"
        params.append(status)
    if assessment_key is not None:
        query += " AND a.assessment_key = ?"
        params.append(assessment_key)
    if assessment_type is not None:
        query += " AND a.assessment_type = ?"
        params.append(assessment_type)
    if content_version is not None:
        query += " AND a.content_version = ?"
        params.append(content_version)

    query += " ORDER BY a.started_at DESC, a.created_at DESC"

    with get_database_connection(db_path) as connection:
        rows = connection.execute(query, tuple(params)).fetchall()

    return [_assessment_from_row(row) for row in rows]


def get_assessment_questions(
    assessment_id: str,
    profile_id: str,
    db_path: str | Path | None = None,
) -> list[AssessmentQuestion]:
    """Return the current content for a saved assessment's question IDs."""

    with get_database_connection(db_path) as connection:
        row = _get_owned_assessment_row(
            connection, assessment_id, profile_id
        )
        question_ids = _json_load(row["question_ids"], [])

    if not isinstance(question_ids, list):
        return []

    questions: list[AssessmentQuestion] = []
    for question_id in question_ids:
        question = get_question(str(question_id))
        if question is not None:
            questions.append(question)
    return questions


def get_responses(
    assessment_id: str,
    profile_id: str,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return this profile's responses in assessment order."""

    with get_database_connection(db_path) as connection:
        _get_owned_assessment_row(connection, assessment_id, profile_id)
        rows = connection.execute(
            """
            SELECT *
            FROM skill_assessment_responses
            WHERE assessment_id = ?
            ORDER BY question_order, created_at
            """,
            (assessment_id,),
        ).fetchall()

    return [_response_from_row(row) for row in rows]


def get_response(
    assessment_id: str,
    profile_id: str,
    question_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    with get_database_connection(db_path) as connection:
        _get_owned_assessment_row(connection, assessment_id, profile_id)
        row = connection.execute(
            """
            SELECT *
            FROM skill_assessment_responses
            WHERE assessment_id = ? AND question_id = ?
            """,
            (assessment_id, question_id),
        ).fetchone()

    return _response_from_row(row) if row else None


def save_response(
    assessment_id: str,
    profile_id: str,
    question_id: str,
    response_text: str = "",
    selected_answer: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Save one response with deterministic marking where applicable."""

    assessment_id = _clean_text(assessment_id, "Assessment", 80)
    profile_id = _clean_text(profile_id, "Profile", 80)
    question_id = _clean_text(question_id, "Question", 120)

    response_id = str(uuid4())
    now = _now()

    try:
        with get_database_connection(db_path) as connection:
            assessment_row = _get_owned_assessment_row(
                connection, assessment_id, profile_id
            )
            if assessment_row["status"] != STATUS_IN_PROGRESS:
                raise SkillAssessmentValidationError(
                    "This assessment is already complete."
                )

            question_ids = _json_load(
                assessment_row["question_ids"], []
            )
            if not isinstance(question_ids, list):
                question_ids = []
            if question_id not in question_ids:
                raise SkillAssessmentValidationError(
                    "That question is not part of this assessment."
                )

            question = get_question(question_id)
            if question is None:
                raise SkillAssessmentValidationError(
                    "That assessment question is no longer available."
                )

            duplicate = connection.execute(
                """
                SELECT 1
                FROM skill_assessment_responses
                WHERE assessment_id = ? AND question_id = ?
                """,
                (assessment_id, question_id),
            ).fetchone()
            if duplicate:
                raise DuplicateAssessmentResponse(
                    "This question has already been answered in this assessment."
                )

            if question.question_type == KNOWLEDGE:
                result = score_knowledge_question(
                    question, str(selected_answer or "")
                )
                response_text = ""
                selected = str(selected_answer or "").strip()
            elif question.question_type == PRACTICAL:
                result = evaluate_practical_response(question, response_text)
                response_text = str(response_text or "").strip()
                selected = None
            else:
                raise SkillAssessmentValidationError(
                    "Unsupported assessment question type."
                )

            is_correct = result.get("is_correct")
            stored_correct = (
                None
                if is_correct is None
                else (1 if is_correct is True else 0)
            )
            question_order = question_ids.index(question_id)

            connection.execute(
                """
                INSERT INTO skill_assessment_responses (
                    response_id,
                    assessment_id,
                    question_id,
                    question_text,
                    question_type,
                    question_order,
                    response_text,
                    selected_answer,
                    is_correct,
                    score_awarded,
                    feedback,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response_id,
                    assessment_id,
                    question_id,
                    question.question,
                    question.question_type,
                    question_order,
                    response_text,
                    selected,
                    stored_correct,
                    result.get("score_awarded"),
                    _json_dump(result.get("feedback") or {}),
                    now,
                ),
            )
    except sqlite3.IntegrityError as error:
        raise DuplicateAssessmentResponse(
            "This question has already been answered in this assessment."
        ) from error

    saved = get_response(
        assessment_id,
        profile_id,
        question_id,
        db_path=db_path,
    )
    if saved is None:
        raise SkillAssessmentError(
            "The assessment response could not be loaded after saving."
        )
    return saved


def complete_assessment(
    assessment_id: str,
    profile_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Mark a fully answered attempt complete and store its score.

    Knowledge questions are scored deterministically. Practical-only
    assessments are stored as completed with no score or proficiency band.
    """

    with get_database_connection(db_path) as connection:
        assessment_row = _get_owned_assessment_row(
            connection, assessment_id, profile_id
        )

        if assessment_row["status"] != STATUS_COMPLETED:
            question_ids = _json_load(assessment_row["question_ids"], [])
            if not isinstance(question_ids, list) or not question_ids:
                raise SkillAssessmentValidationError(
                    "This assessment has no questions to complete."
                )

            response_rows = connection.execute(
                """
                SELECT *
                FROM skill_assessment_responses
                WHERE assessment_id = ?
                ORDER BY question_order, created_at
                """,
                (assessment_id,),
            ).fetchall()
            answered_ids = {
                str(row["question_id"]) for row in response_rows
            }
            missing = [
                question_id
                for question_id in question_ids
                if str(question_id) not in answered_ids
            ]
            if missing:
                raise SkillAssessmentValidationError(
                    "Answer every question before finishing the assessment."
                )

            knowledge_rows = [
                row
                for row in response_rows
                if str(row["question_type"]) == KNOWLEDGE
            ]
            correct = sum(
                1
                for row in knowledge_rows
                if bool(row["is_correct"])
            )
            score = (
                score_to_percentage(correct, len(knowledge_rows))
                if knowledge_rows
                else None
            )
            band = proficiency_band(score)
            proficiency_level = band["label"] if band else None

            now = _now()
            connection.execute(
                """
                UPDATE skill_assessments
                SET
                    status = ?,
                    score = ?,
                    proficiency_level = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE assessment_id = ? AND profile_id = ?
                """,
                (
                    STATUS_COMPLETED,
                    score,
                    proficiency_level,
                    now,
                    now,
                    assessment_id,
                    profile_id,
                ),
            )

    completed = get_assessment(
        assessment_id, profile_id, db_path=db_path
    )
    if completed is None:
        raise SkillAssessmentNotFound(
            "That skill assessment could not be found after completion."
        )
    return completed


def list_comparable_assessments(
    profile_id: str,
    assessment_key: str,
    assessment_type: str,
    content_version: str,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return completed, scored attempts that use the same content and method."""

    attempts = list_assessments(
        profile_id,
        status=STATUS_COMPLETED,
        assessment_key=assessment_key,
        assessment_type=assessment_type,
        content_version=content_version,
        db_path=db_path,
    )
    return [
        attempt
        for attempt in attempts
        if attempt.get("score") is not None
    ]


def delete_assessment(
    assessment_id: str,
    profile_id: str,
    db_path: str | Path | None = None,
) -> bool:
    """Delete one attempt and its responses, keeping other attempts intact."""

    with get_database_connection(db_path) as connection:
        _get_owned_assessment_row(connection, assessment_id, profile_id)
        cursor = connection.execute(
            """
            DELETE FROM skill_assessments
            WHERE assessment_id = ? AND profile_id = ?
            """,
            (assessment_id, profile_id),
        )
    return cursor.rowcount == 1


__all__ = [
    "DuplicateAssessmentResponse",
    "SkillAssessmentNotFound",
    "complete_assessment",
    "create_assessment",
    "delete_assessment",
    "get_assessment",
    "get_assessment_questions",
    "get_response",
    "get_responses",
    "list_assessments",
    "list_comparable_assessments",
    "save_response",
]
