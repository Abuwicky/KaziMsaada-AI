"""SQLite persistence for the Mentor Meeting Centre.

Every public operation accepts an optional ``db_path`` so tests can use an
isolated database. The production database remains the single existing
``data/kazimsaada.db`` file.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .database import get_database_connection
from .workspace import get_current_owner_id, normalize_owner_id
from .mentor_access import generate_access_code, hash_access_code, verify_access_code
from .mentors import (
    APPLICATION_APPROVED,
    APPLICATION_PENDING,
    APPLICATION_REJECTED,
    APPLICATION_STATUSES,
    AVAILABILITY_BOOKED,
    AVAILABILITY_OPEN,
    AVAILABILITY_REMOVED,
    BOOKING_CANCELLED,
    BOOKING_COMPLETED,
    BOOKING_CONFIRMED,
    BOOKING_PENDING,
    BOOKING_REJECTED,
    DEFAULT_DURATION_OPTIONS,
    DURATION_OPTIONS,
    MentorConflictError,
    MentorNotFoundError,
    MentorPermissionError,
    MentorValidationError,
    clean_https_url,
    clean_duration_options,
    is_future,
    new_booking_reference,
    now_utc_iso,
    parse_utc,
    to_utc_iso,
    validate_application,
    validate_booking_request,
    validate_feedback,
    validate_mentor_profile,
    validate_reschedule_note,
    validate_review_note,
    utc_now,
)

BOOKING_SELECT = """
    SELECT
        b.*,
        m.full_name AS mentor_name,
        m.professional_title AS mentor_title,
        m.industry AS mentor_industry,
        m.specialisation AS mentor_specialisation,
        p.name AS job_seeker_name,
        p.career_interest AS job_seeker_interest,
        f.feedback_id AS feedback_id,
        f.rating AS feedback_rating,
        f.comment AS feedback_comment,
        f.helpful AS feedback_helpful,
        f.further_support AS feedback_further_support,
        f.created_at AS feedback_created_at
    FROM mentor_bookings b
    JOIN mentor_profiles m ON m.mentor_id = b.mentor_id
    JOIN job_seekers p ON p.profile_id = b.profile_id
    LEFT JOIN mentor_feedback f ON f.booking_id = b.booking_id
"""


def _json_load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _clean_id(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise MentorValidationError(f"{label} is required.")
    if len(text) > 100:
        raise MentorValidationError(f"{label} is invalid.")
    return text


def _application_from_row(row: sqlite3.Row) -> dict[str, Any]:
    application = dict(row)
    application["areas_of_expertise"] = _json_load(
        application.get("areas_of_expertise"), []
    )
    application["languages"] = _json_load(application.get("languages"), [])
    return application


def _mentor_from_row(row: sqlite3.Row) -> dict[str, Any]:
    mentor = dict(row)
    mentor["languages"] = _json_load(mentor.get("languages"), [])
    mentor["coaching_areas"] = _json_load(mentor.get("coaching_areas"), [])
    mentor["duration_options"] = _json_load(
        mentor.get("duration_options"), list(DEFAULT_DURATION_OPTIONS)
    )
    return mentor


def _public_mentor(mentor: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "mentor_id",
        "full_name",
        "professional_title",
        "biography",
        "industry",
        "specialisation",
        "experience",
        "qualifications",
        "languages",
        "coaching_areas",
        "duration_options",
        "avatar_url",
        "created_at",
        "updated_at",
    )
    return {key: mentor.get(key) for key in keys}


def _availability_from_row(row: sqlite3.Row) -> dict[str, Any]:
    slot = dict(row)
    slot["duration_minutes"] = int(slot.get("duration_minutes") or 0)
    return slot


def _booking_from_row(row: sqlite3.Row) -> dict[str, Any]:
    booking = dict(row)
    booking["duration_minutes"] = int(booking.get("duration_minutes") or 0)
    feedback_id = booking.pop("feedback_id", None)
    rating = booking.pop("feedback_rating", None)
    comment = booking.pop("feedback_comment", None)
    helpful = booking.pop("feedback_helpful", None)
    further_support = booking.pop("feedback_further_support", None)
    feedback_created_at = booking.pop("feedback_created_at", None)
    booking["feedback"] = None
    if feedback_id:
        booking["feedback"] = {
            "feedback_id": feedback_id,
            "rating": int(rating or 0),
            "comment": comment or "",
            "helpful": bool(helpful),
            "further_support": further_support or "",
            "created_at": feedback_created_at,
        }
    return booking


def _feedback_from_row(row: sqlite3.Row) -> dict[str, Any]:
    feedback = dict(row)
    feedback["rating"] = int(feedback.get("rating") or 0)
    feedback["helpful"] = bool(feedback.get("helpful"))
    return feedback


def _require_application(
    connection: sqlite3.Connection,
    application_id: str,
    *,
    include_all: bool = False,
) -> sqlite3.Row:
    query = "SELECT * FROM mentor_applications WHERE application_id = ?"
    parameters: list[Any] = [application_id]
    if not include_all:
        query += " AND owner_id = ?"
        parameters.append(normalize_owner_id(get_current_owner_id()))
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise MentorNotFoundError("That mentor application could not be found.")
    return row


def _require_mentor(
    connection: sqlite3.Connection,
    mentor_id: str,
    *,
    approved_only: bool = False,
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM mentor_profiles WHERE mentor_id = ?",
        (mentor_id,),
    ).fetchone()
    if row is None:
        raise MentorNotFoundError("That mentor could not be found.")
    if approved_only and row["approval_status"] != "approved":
        raise MentorNotFoundError("That mentor is not currently available.")
    return row


def _require_profile(connection: sqlite3.Connection, profile_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM job_seekers WHERE profile_id = ? AND owner_id = ?",
        (profile_id, normalize_owner_id(get_current_owner_id())),
    ).fetchone()
    if row is None:
        raise MentorValidationError("The active profile could not be found.")
    return row


def _require_slot(connection: sqlite3.Connection, slot_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM mentor_availability WHERE slot_id = ?",
        (slot_id,),
    ).fetchone()
    if row is None:
        raise MentorNotFoundError("That availability slot could not be found.")
    return row


def _require_booking(
    connection: sqlite3.Connection,
    booking_id: str,
    *,
    profile_id: str | None = None,
    mentor_id: str | None = None,
) -> sqlite3.Row:
    query = BOOKING_SELECT + " WHERE b.booking_id = ?"
    parameters: list[Any] = [booking_id]
    if profile_id is not None:
        query += " AND b.profile_id = ? AND p.owner_id = ?"
        parameters.extend([profile_id, normalize_owner_id(get_current_owner_id())])
    if mentor_id is not None:
        query += " AND b.mentor_id = ?"
        parameters.append(mentor_id)
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        if profile_id is not None or mentor_id is not None:
            raise MentorNotFoundError(
                "That booking could not be found for this account."
            )
        raise MentorNotFoundError("That booking could not be found.")
    return row


def _mentor_duration_options(connection: sqlite3.Connection, mentor_id: str) -> list[int]:
    row = _require_mentor(connection, mentor_id, approved_only=True)
    return clean_duration_options(_json_load(row["duration_options"], []))


def _check_slot_overlap(
    connection: sqlite3.Connection,
    mentor_id: str,
    start_iso: str,
    end_iso: str,
    *,
    exclude_slot_id: str | None = None,
) -> None:
    query = """
        SELECT 1
        FROM mentor_availability
        WHERE mentor_id = ?
          AND status != ?
          AND start_at_utc < ?
          AND end_at_utc > ?
    """
    parameters: list[Any] = [
        mentor_id,
        AVAILABILITY_REMOVED,
        end_iso,
        start_iso,
    ]
    if exclude_slot_id:
        query += " AND slot_id != ?"
        parameters.append(exclude_slot_id)
    if connection.execute(query, parameters).fetchone():
        raise MentorConflictError(
            "That time overlaps another availability slot for this mentor."
        )


def _reopen_slot(connection: sqlite3.Connection, slot_id: str) -> None:
    slot = connection.execute(
        "SELECT status FROM mentor_availability WHERE slot_id = ?",
        (slot_id,),
    ).fetchone()
    if slot is None or slot["status"] == AVAILABILITY_REMOVED:
        return
    active = connection.execute(
        """
        SELECT 1
        FROM mentor_bookings
        WHERE availability_id = ?
          AND status IN (?, ?)
        """,
        (slot_id, BOOKING_PENDING, BOOKING_CONFIRMED),
    ).fetchone()
    if active is None:
        connection.execute(
            "UPDATE mentor_availability SET status = ?, updated_at = ? WHERE slot_id = ?",
            (AVAILABILITY_OPEN, now_utc_iso(), slot_id),
        )


def create_mentor_application(
    data: dict,
    applicant_profile_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    cleaned = validate_application(data)
    profile_id = str(applicant_profile_id or "").strip() or None
    owner = normalize_owner_id(get_current_owner_id())
    now = now_utc_iso()
    application_id = str(uuid4())

    with get_database_connection(db_path) as connection:
        if profile_id:
            _require_profile(connection, profile_id)
        try:
            connection.execute(
                """
                INSERT INTO mentor_applications (
                    application_id,
                    owner_id,
                    applicant_profile_id,
                    full_name,
                    email,
                    professional_title,
                    industry,
                    specialisation,
                    areas_of_expertise,
                    experience,
                    biography,
                    qualifications,
                    languages,
                    supporting_info,
                    avatar_url,
                    status,
                    review_note,
                    reviewed_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    owner,
                    profile_id,
                    cleaned["full_name"],
                    cleaned["email"],
                    cleaned["professional_title"],
                    cleaned["industry"],
                    cleaned["specialisation"],
                    _json_dump(cleaned["areas_of_expertise"]),
                    cleaned["experience"],
                    cleaned["biography"],
                    cleaned["qualifications"],
                    _json_dump(cleaned["languages"]),
                    cleaned["supporting_info"],
                    cleaned["avatar_url"],
                    APPLICATION_PENDING,
                    None,
                    None,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise MentorConflictError(
                "A pending mentor application already exists for that email address."
            ) from error

    application = get_mentor_application(application_id, db_path=db_path)
    if application is None:
        raise MentorNotFoundError("The application could not be loaded after saving.")
    return application


def get_mentor_application(
    application_id: str,
    db_path: str | Path | None = None,
    *,
    include_all: bool = False,
) -> dict[str, Any] | None:
    with get_database_connection(db_path) as connection:
        row = _require_application(
            connection,
            application_id,
            include_all=include_all,
        )
    return _application_from_row(row) if row else None


def list_mentor_applications(
    status: str | None = None,
    db_path: str | Path | None = None,
    *,
    include_all: bool = False,
) -> list[dict[str, Any]]:
    if status is not None and status not in APPLICATION_STATUSES:
        raise MentorValidationError("Choose a valid application status.")
    conditions: list[str] = []
    parameters: list[Any] = []
    if status:
        conditions.append("status = ?")
        parameters.append(status)
    if not include_all:
        conditions.append("owner_id = ?")
        parameters.append(normalize_owner_id(get_current_owner_id()))
    query = "SELECT * FROM mentor_applications"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC"
    with get_database_connection(db_path) as connection:
        rows = connection.execute(query, tuple(parameters)).fetchall()
    return [_application_from_row(row) for row in rows]


def list_applications_for_profile(
    profile_id: str,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    profile_id = _clean_id(profile_id, "Profile")
    owner = normalize_owner_id(get_current_owner_id())
    with get_database_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM mentor_applications
            WHERE applicant_profile_id = ? AND owner_id = ?
            ORDER BY created_at DESC
            """,
            (profile_id, owner),
        ).fetchall()
    return [_application_from_row(row) for row in rows]


def review_mentor_application(
    application_id: str,
    decision: str,
    review_note: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Approve or reject an application.

    The caller is responsible for enforcing administrator access. This function
    intentionally does not treat profile selection as an authentication check.
    """

    decision = str(decision or "").strip().lower()
    if decision not in (APPLICATION_APPROVED, APPLICATION_REJECTED):
        raise MentorValidationError("Choose approve or reject.")
    note = validate_review_note(review_note)
    now = now_utc_iso()

    with get_database_connection(db_path) as connection:
        application = _require_application(
            connection,
            application_id,
            include_all=True,
        )
        if application["status"] != APPLICATION_PENDING:
            raise MentorConflictError("That application has already been reviewed.")

        if decision == APPLICATION_REJECTED:
            connection.execute(
                """
                UPDATE mentor_applications
                SET status = ?, review_note = ?, reviewed_at = ?, updated_at = ?
                WHERE application_id = ?
                """,
                (APPLICATION_REJECTED, note, now, now, application_id),
            )
            return {
                "application": get_mentor_application(
                    application_id,
                    db_path=db_path,
                    include_all=True,
                ),
                "mentor": None,
                "access_code": None,
            }

        data = _application_from_row(application)
        mentor_id = str(uuid4())
        raw_code = generate_access_code()
        options = _json_dump(list(DEFAULT_DURATION_OPTIONS))
        connection.execute(
            """
            INSERT INTO mentor_profiles (
                mentor_id,
                application_id,
                full_name,
                professional_title,
                biography,
                industry,
                specialisation,
                experience,
                qualifications,
                languages,
                coaching_areas,
                duration_options,
                avatar_url,
                approval_status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mentor_id,
                application_id,
                data["full_name"],
                data["professional_title"],
                data["biography"],
                data["industry"],
                data["specialisation"],
                data["experience"],
                data["qualifications"],
                _json_dump(data["languages"]),
                _json_dump(data["areas_of_expertise"]),
                options,
                data.get("avatar_url") or "",
                APPLICATION_APPROVED,
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO mentor_access (
                mentor_id, access_code_hash, created_at, rotated_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (mentor_id, hash_access_code(raw_code), now, None),
        )
        connection.execute(
            """
            UPDATE mentor_applications
            SET status = ?, review_note = ?, reviewed_at = ?, updated_at = ?
            WHERE application_id = ?
            """,
            (APPLICATION_APPROVED, note, now, now, application_id),
        )

    return {
        "application": get_mentor_application(
            application_id,
            db_path=db_path,
            include_all=True,
        ),
        "mentor": get_mentor_workspace(mentor_id, db_path=db_path),
        "access_code": raw_code,
    }


def list_public_mentors(
    search: str = "",
    industry: str = "",
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM mentor_profiles WHERE approval_status = ?"
    parameters: list[Any] = [APPLICATION_APPROVED]
    industry = str(industry or "").strip()
    if industry and industry.casefold() not in {"all", "all industries"}:
        query += " AND lower(industry) = lower(?)"
        parameters.append(industry)
    search = str(search or "").strip()
    if search:
        pattern = f"%{search}%"
        query += """
            AND (
                full_name LIKE ?
                OR professional_title LIKE ?
                OR industry LIKE ?
                OR specialisation LIKE ?
                OR coaching_areas LIKE ?
                OR languages LIKE ?
            )
        """
        parameters.extend([pattern] * 6)
    query += " ORDER BY full_name COLLATE NOCASE"
    with get_database_connection(db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [_public_mentor(_mentor_from_row(row)) for row in rows]


def list_public_industries(db_path: str | Path | None = None) -> list[str]:
    with get_database_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT industry
            FROM mentor_profiles
            WHERE approval_status = ?
            ORDER BY industry COLLATE NOCASE
            """,
            (APPLICATION_APPROVED,),
        ).fetchall()
    return [str(row["industry"]) for row in rows if str(row["industry"]).strip()]


def get_public_mentor(
    mentor_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    mentor_id = _clean_id(mentor_id, "Mentor")
    with get_database_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM mentor_profiles
            WHERE mentor_id = ? AND approval_status = ?
            """,
            (mentor_id, APPLICATION_APPROVED),
        ).fetchone()
    return _public_mentor(_mentor_from_row(row)) if row else None


def get_mentor_by_application(
    application_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    application_id = _clean_id(application_id, "Application")
    with get_database_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM mentor_profiles WHERE application_id = ?",
            (application_id,),
        ).fetchone()
    return _mentor_from_row(row) if row else None


def get_mentor_workspace(
    mentor_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    mentor_id = _clean_id(mentor_id, "Mentor")
    with get_database_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM mentor_profiles WHERE mentor_id = ?",
            (mentor_id,),
        ).fetchone()
    return _mentor_from_row(row) if row else None


def authenticate_mentor(
    access_code: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return an approved mentor workspace for a valid access code."""

    code = str(access_code or "").strip()
    if not code:
        return None
    with get_database_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT a.mentor_id, a.access_code_hash, m.approval_status
            FROM mentor_access a
            JOIN mentor_profiles m ON m.mentor_id = a.mentor_id
            WHERE m.approval_status = ?
            """,
            (APPLICATION_APPROVED,),
        ).fetchall()
    for row in rows:
        if verify_access_code(code, row["access_code_hash"]):
            return get_mentor_workspace(row["mentor_id"], db_path=db_path)
    return None


def rotate_mentor_access_code(
    mentor_id: str,
    db_path: str | Path | None = None,
) -> str:
    mentor_id = _clean_id(mentor_id, "Mentor")
    raw_code = generate_access_code()
    now = now_utc_iso()
    with get_database_connection(db_path) as connection:
        _require_mentor(connection, mentor_id)
        cursor = connection.execute(
            """
            UPDATE mentor_access
            SET access_code_hash = ?, rotated_at = ?
            WHERE mentor_id = ?
            """,
            (hash_access_code(raw_code), now, mentor_id),
        )
        if cursor.rowcount == 0:
            raise MentorNotFoundError("Mentor access is not configured.")
    return raw_code


def update_mentor_profile(
    mentor_id: str,
    data: dict,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    cleaned = validate_mentor_profile(data)
    mentor_id = _clean_id(mentor_id, "Mentor")
    now = now_utc_iso()
    with get_database_connection(db_path) as connection:
        _require_mentor(connection, mentor_id, approved_only=True)
        connection.execute(
            """
            UPDATE mentor_profiles
            SET full_name = ?,
                professional_title = ?,
                biography = ?,
                industry = ?,
                specialisation = ?,
                experience = ?,
                qualifications = ?,
                languages = ?,
                coaching_areas = ?,
                duration_options = ?,
                avatar_url = ?,
                updated_at = ?
            WHERE mentor_id = ?
            """,
            (
                cleaned["full_name"],
                cleaned["professional_title"],
                cleaned["biography"],
                cleaned["industry"],
                cleaned["specialisation"],
                cleaned["experience"],
                cleaned["qualifications"],
                _json_dump(cleaned["languages"]),
                _json_dump(cleaned["coaching_areas"]),
                _json_dump(cleaned["duration_options"]),
                cleaned["avatar_url"],
                now,
                mentor_id,
            ),
        )
    mentor = get_mentor_workspace(mentor_id, db_path=db_path)
    if mentor is None:
        raise MentorNotFoundError("The mentor profile could not be loaded.")
    return mentor


def create_availability(
    mentor_id: str,
    start_at_utc: str,
    duration_minutes: int,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    try:
        duration = int(duration_minutes)
    except (TypeError, ValueError) as error:
        raise MentorValidationError("Choose a valid session duration.") from error
    start = parse_utc(start_at_utc)
    if duration not in DURATION_OPTIONS:
        raise MentorValidationError("Choose a valid session duration.")
    if not is_future(start):
        raise MentorValidationError("Availability must be in the future.")
    if start > utc_now() + timedelta(days=365):
        raise MentorValidationError("Availability must be within the next year.")
    end = start + timedelta(minutes=duration)
    start_iso = to_utc_iso(start)
    end_iso = to_utc_iso(end)
    now = now_utc_iso()

    with get_database_connection(db_path) as connection:
        options = _mentor_duration_options(connection, mentor_id)
        if duration not in options:
            allowed = ", ".join(str(item) for item in options)
            raise MentorValidationError(
                f"This mentor offers {allowed}-minute sessions."
            )
        _check_slot_overlap(connection, mentor_id, start_iso, end_iso)
        slot_id = str(uuid4())
        try:
            connection.execute(
                """
                INSERT INTO mentor_availability (
                    slot_id,
                    mentor_id,
                    start_at_utc,
                    end_at_utc,
                    duration_minutes,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slot_id,
                    mentor_id,
                    start_iso,
                    end_iso,
                    duration,
                    AVAILABILITY_OPEN,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise MentorConflictError(
                "That availability slot already exists."
            ) from error

    return get_availability(slot_id, mentor_id, db_path=db_path)


def get_availability(
    slot_id: str,
    mentor_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    slot_id = _clean_id(slot_id, "Availability slot")
    mentor_id = _clean_id(mentor_id, "Mentor")
    with get_database_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT * FROM mentor_availability
            WHERE slot_id = ? AND mentor_id = ?
            """,
            (slot_id, mentor_id),
        ).fetchone()
    if row is None:
        raise MentorNotFoundError("That availability slot could not be found.")
    return _availability_from_row(row)


def update_availability(
    mentor_id: str,
    slot_id: str,
    start_at_utc: str,
    duration_minutes: int,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    slot_id = _clean_id(slot_id, "Availability slot")
    try:
        duration = int(duration_minutes)
    except (TypeError, ValueError) as error:
        raise MentorValidationError("Choose a valid session duration.") from error
    if duration not in DURATION_OPTIONS:
        raise MentorValidationError("Choose a valid session duration.")
    start = parse_utc(start_at_utc)
    if not is_future(start):
        raise MentorValidationError("Availability must be in the future.")
    end = start + timedelta(minutes=duration)
    start_iso = to_utc_iso(start)
    end_iso = to_utc_iso(end)
    now = now_utc_iso()

    with get_database_connection(db_path) as connection:
        options = _mentor_duration_options(connection, mentor_id)
        if duration not in options:
            raise MentorValidationError("Choose a duration offered on this profile.")
        slot = _require_slot(connection, slot_id)
        if slot["mentor_id"] != mentor_id:
            raise MentorPermissionError("That slot belongs to another mentor.")
        if slot["status"] != AVAILABILITY_OPEN:
            raise MentorConflictError("Only open availability can be edited.")
        active = connection.execute(
            """
            SELECT 1 FROM mentor_bookings
            WHERE availability_id = ? AND status IN (?, ?)
            """,
            (slot_id, BOOKING_PENDING, BOOKING_CONFIRMED),
        ).fetchone()
        if active:
            raise MentorConflictError("Booked availability cannot be edited.")
        _check_slot_overlap(
            connection,
            mentor_id,
            start_iso,
            end_iso,
            exclude_slot_id=slot_id,
        )
        connection.execute(
            """
            UPDATE mentor_availability
            SET start_at_utc = ?, end_at_utc = ?, duration_minutes = ?, updated_at = ?
            WHERE slot_id = ?
            """,
            (start_iso, end_iso, duration, now, slot_id),
        )
    return get_availability(slot_id, mentor_id, db_path=db_path)


def remove_availability(
    mentor_id: str,
    slot_id: str,
    db_path: str | Path | None = None,
) -> None:
    mentor_id = _clean_id(mentor_id, "Mentor")
    slot_id = _clean_id(slot_id, "Availability slot")
    now = now_utc_iso()
    with get_database_connection(db_path) as connection:
        _require_mentor(connection, mentor_id)
        slot = _require_slot(connection, slot_id)
        if slot["mentor_id"] != mentor_id:
            raise MentorPermissionError("That slot belongs to another mentor.")
        active = connection.execute(
            """
            SELECT 1 FROM mentor_bookings
            WHERE availability_id = ? AND status IN (?, ?)
            """,
            (slot_id, BOOKING_PENDING, BOOKING_CONFIRMED),
        ).fetchone()
        if active:
            raise MentorConflictError(
                "Cancel or resolve the active booking before removing this slot."
            )
        connection.execute(
            """
            UPDATE mentor_availability
            SET status = ?, updated_at = ?
            WHERE slot_id = ?
            """,
            (AVAILABILITY_REMOVED, now, slot_id),
        )


def list_mentor_availability(
    mentor_id: str,
    *,
    include_past: bool = True,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    query = "SELECT * FROM mentor_availability WHERE mentor_id = ?"
    parameters: list[Any] = [mentor_id]
    if not include_past:
        query += " AND start_at_utc > ?"
        parameters.append(now_utc_iso())
    query += " ORDER BY start_at_utc"
    with get_database_connection(db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [_availability_from_row(row) for row in rows]


def list_open_slots(
    mentor_id: str,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    with get_database_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM mentor_availability
            WHERE mentor_id = ? AND status = ? AND start_at_utc > ?
            ORDER BY start_at_utc
            """,
            (mentor_id, AVAILABILITY_OPEN, now_utc_iso()),
        ).fetchall()
    return [_availability_from_row(row) for row in rows]


def create_booking(
    profile_id: str,
    mentor_id: str,
    availability_id: str,
    purpose: str,
    target_job_role: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    profile_id = _clean_id(profile_id, "Profile")
    mentor_id = _clean_id(mentor_id, "Mentor")
    availability_id = _clean_id(availability_id, "Availability slot")
    details = validate_booking_request(purpose, target_job_role)
    now = now_utc_iso()

    with get_database_connection(db_path) as connection:
        _require_profile(connection, profile_id)
        _require_mentor(connection, mentor_id, approved_only=True)
        slot = _require_slot(connection, availability_id)
        if slot["mentor_id"] != mentor_id:
            raise MentorValidationError("That slot belongs to another mentor.")
        if slot["status"] != AVAILABILITY_OPEN:
            raise MentorConflictError("That time is no longer available.")
        if not is_future(slot["start_at_utc"]):
            raise MentorConflictError("That time has already passed.")
        active = connection.execute(
            """
            SELECT 1 FROM mentor_bookings
            WHERE availability_id = ? AND status IN (?, ?)
            """,
            (availability_id, BOOKING_PENDING, BOOKING_CONFIRMED),
        ).fetchone()
        if active:
            raise MentorConflictError("That time is no longer available.")

        booking_id = str(uuid4())
        reference = new_booking_reference()
        for attempt in range(4):
            try:
                connection.execute(
                    """
                    INSERT INTO mentor_bookings (
                        booking_id,
                        booking_reference,
                        profile_id,
                        mentor_id,
                        availability_id,
                        status,
                        purpose,
                        target_job_role,
                        scheduled_start_utc,
                        scheduled_end_utc,
                        duration_minutes,
                        meeting_link,
                        mentor_recommendations,
                        reschedule_requested_at,
                        reschedule_note,
                        cancellation_reason,
                        created_at,
                        updated_at,
                        confirmed_at,
                        cancelled_at,
                        completed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        booking_id,
                        reference,
                        profile_id,
                        mentor_id,
                        availability_id,
                        BOOKING_PENDING,
                        details["purpose"],
                        details["target_job_role"],
                        slot["start_at_utc"],
                        slot["end_at_utc"],
                        slot["duration_minutes"],
                        None,
                        "",
                        None,
                        None,
                        None,
                        now,
                        now,
                        None,
                        None,
                        None,
                    ),
                )
                break
            except sqlite3.IntegrityError as error:
                if attempt == 3:
                    raise MentorConflictError(
                        "That time was just booked by another user. Choose another slot."
                    ) from error
                reference = new_booking_reference()

        connection.execute(
            """
            UPDATE mentor_availability
            SET status = ?, updated_at = ?
            WHERE slot_id = ?
            """,
            (AVAILABILITY_BOOKED, now, availability_id),
        )

    return get_booking(booking_id, profile_id=profile_id, db_path=db_path)


def get_booking(
    booking_id: str,
    *,
    profile_id: str | None = None,
    mentor_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    if not profile_id and not mentor_id:
        raise MentorPermissionError("Identify the booking participant.")
    with get_database_connection(db_path) as connection:
        row = _require_booking(
            connection,
            booking_id,
            profile_id=profile_id,
            mentor_id=mentor_id,
        )
    return _booking_from_row(row)


def list_bookings_for_profile(
    profile_id: str,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    profile_id = _clean_id(profile_id, "Profile")
    with get_database_connection(db_path) as connection:
        rows = connection.execute(
            BOOKING_SELECT
            + " WHERE b.profile_id = ? AND p.owner_id = ? ORDER BY b.created_at DESC",
            (profile_id, normalize_owner_id(get_current_owner_id())),
        ).fetchall()
    return [_booking_from_row(row) for row in rows]


def list_bookings_for_mentor(
    mentor_id: str,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    with get_database_connection(db_path) as connection:
        rows = connection.execute(
            BOOKING_SELECT
            + " WHERE b.mentor_id = ? ORDER BY b.created_at DESC",
            (mentor_id,),
        ).fetchall()
    return [_booking_from_row(row) for row in rows]


def confirm_booking(
    booking_id: str,
    mentor_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    now = now_utc_iso()
    with get_database_connection(db_path) as connection:
        booking = _require_booking(connection, booking_id, mentor_id=mentor_id)
        if booking["status"] != BOOKING_PENDING:
            raise MentorConflictError("Only pending bookings can be confirmed.")
        connection.execute(
            """
            UPDATE mentor_bookings
            SET status = ?, confirmed_at = ?, updated_at = ?
            WHERE booking_id = ?
            """,
            (BOOKING_CONFIRMED, now, now, booking_id),
        )
    return get_booking(booking_id, mentor_id=mentor_id, db_path=db_path)


def reject_booking(
    booking_id: str,
    mentor_id: str,
    reason: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    reason = validate_review_note(reason)
    now = now_utc_iso()
    with get_database_connection(db_path) as connection:
        booking = _require_booking(connection, booking_id, mentor_id=mentor_id)
        if booking["status"] != BOOKING_PENDING:
            raise MentorConflictError("Only pending bookings can be rejected.")
        connection.execute(
            """
            UPDATE mentor_bookings
            SET status = ?, cancellation_reason = ?, updated_at = ?
            WHERE booking_id = ?
            """,
            (BOOKING_REJECTED, reason, now, booking_id),
        )
        _reopen_slot(connection, booking["availability_id"])
    return get_booking(booking_id, mentor_id=mentor_id, db_path=db_path)


def cancel_booking(
    booking_id: str,
    *,
    profile_id: str | None = None,
    mentor_id: str | None = None,
    reason: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if bool(profile_id) == bool(mentor_id):
        raise MentorPermissionError("Identify either the job seeker or the mentor.")
    reason = validate_review_note(reason)
    now = now_utc_iso()
    with get_database_connection(db_path) as connection:
        booking = _require_booking(
            connection,
            booking_id,
            profile_id=profile_id,
            mentor_id=mentor_id,
        )
        if booking["status"] not in (BOOKING_PENDING, BOOKING_CONFIRMED):
            raise MentorConflictError("This booking can no longer be cancelled.")
        if not is_future(booking["scheduled_start_utc"]):
            raise MentorConflictError("Past meetings cannot be cancelled.")
        connection.execute(
            """
            UPDATE mentor_bookings
            SET status = ?, cancellation_reason = ?, cancelled_at = ?, updated_at = ?
            WHERE booking_id = ?
            """,
            (BOOKING_CANCELLED, reason, now, now, booking_id),
        )
        _reopen_slot(connection, booking["availability_id"])
    actor_key = "profile_id" if profile_id else "mentor_id"
    actor_value = profile_id or mentor_id
    return get_booking(
        booking_id,
        **{actor_key: actor_value},
        db_path=db_path,
    )


def complete_booking(
    booking_id: str,
    mentor_id: str,
    recommendations: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    recommendations = validate_review_note(recommendations)
    now = now_utc_iso()
    with get_database_connection(db_path) as connection:
        booking = _require_booking(connection, booking_id, mentor_id=mentor_id)
        if booking["status"] != BOOKING_CONFIRMED:
            raise MentorConflictError("Only confirmed bookings can be completed.")
        if parse_utc(booking["scheduled_end_utc"]) > utc_now():
            raise MentorConflictError(
                "The meeting can be marked complete after its scheduled end time."
            )
        connection.execute(
            """
            UPDATE mentor_bookings
            SET status = ?,
                mentor_recommendations = ?,
                completed_at = ?,
                updated_at = ?
            WHERE booking_id = ?
            """,
            (BOOKING_COMPLETED, recommendations, now, now, booking_id),
        )
    return get_booking(booking_id, mentor_id=mentor_id, db_path=db_path)


def update_mentor_recommendations(
    booking_id: str,
    mentor_id: str,
    recommendations: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    recommendations = validate_review_note(recommendations)
    with get_database_connection(db_path) as connection:
        booking = _require_booking(connection, booking_id, mentor_id=mentor_id)
        if booking["status"] != BOOKING_COMPLETED:
            raise MentorConflictError(
                "Recommendations can be added after the meeting is completed."
            )
        connection.execute(
            """
            UPDATE mentor_bookings
            SET mentor_recommendations = ?, updated_at = ?
            WHERE booking_id = ?
            """,
            (recommendations, now_utc_iso(), booking_id),
        )
    return get_booking(booking_id, mentor_id=mentor_id, db_path=db_path)


def request_reschedule(
    booking_id: str,
    profile_id: str,
    note: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    profile_id = _clean_id(profile_id, "Profile")
    note = validate_reschedule_note(note)
    with get_database_connection(db_path) as connection:
        booking = _require_booking(connection, booking_id, profile_id=profile_id)
        if booking["status"] not in (BOOKING_PENDING, BOOKING_CONFIRMED):
            raise MentorConflictError("This booking cannot be rescheduled.")
        if not is_future(booking["scheduled_start_utc"]):
            raise MentorConflictError("Past meetings cannot be rescheduled.")
        connection.execute(
            """
            UPDATE mentor_bookings
            SET reschedule_requested_at = ?, reschedule_note = ?, updated_at = ?
            WHERE booking_id = ?
            """,
            (now_utc_iso(), note, now_utc_iso(), booking_id),
        )
    return get_booking(booking_id, profile_id=profile_id, db_path=db_path)


def clear_reschedule_request(
    booking_id: str,
    mentor_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    with get_database_connection(db_path) as connection:
        _require_booking(connection, booking_id, mentor_id=mentor_id)
        connection.execute(
            """
            UPDATE mentor_bookings
            SET reschedule_requested_at = NULL, reschedule_note = NULL, updated_at = ?
            WHERE booking_id = ?
            """,
            (now_utc_iso(), booking_id),
        )
    return get_booking(booking_id, mentor_id=mentor_id, db_path=db_path)


def update_meeting_link(
    booking_id: str,
    mentor_id: str,
    meeting_url: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    mentor_id = _clean_id(mentor_id, "Mentor")
    url = clean_https_url(meeting_url, "Meeting link")
    with get_database_connection(db_path) as connection:
        booking = _require_booking(connection, booking_id, mentor_id=mentor_id)
        if booking["status"] != BOOKING_CONFIRMED:
            raise MentorConflictError(
                "A meeting link can be added only to a confirmed booking."
            )
        connection.execute(
            """
            UPDATE mentor_bookings
            SET meeting_link = ?, updated_at = ?
            WHERE booking_id = ?
            """,
            (url, now_utc_iso(), booking_id),
        )
    return get_booking(booking_id, mentor_id=mentor_id, db_path=db_path)


def submit_feedback(
    booking_id: str,
    profile_id: str,
    rating,
    comment: str = "",
    helpful: bool = True,
    further_support: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    profile_id = _clean_id(profile_id, "Profile")
    details = validate_feedback(rating, comment, helpful, further_support)
    now = now_utc_iso()
    feedback_id = str(uuid4())
    with get_database_connection(db_path) as connection:
        booking = _require_booking(connection, booking_id, profile_id=profile_id)
        if booking["status"] != BOOKING_COMPLETED:
            raise MentorConflictError(
                "Feedback can be submitted after a completed meeting."
            )
        existing = connection.execute(
            "SELECT 1 FROM mentor_feedback WHERE booking_id = ?",
            (booking_id,),
        ).fetchone()
        if existing:
            raise MentorConflictError("Feedback has already been submitted.")
        try:
            connection.execute(
                """
                INSERT INTO mentor_feedback (
                    feedback_id,
                    booking_id,
                    profile_id,
                    mentor_id,
                    rating,
                    comment,
                    helpful,
                    further_support,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    booking_id,
                    profile_id,
                    booking["mentor_id"],
                    details["rating"],
                    details["comment"],
                    details["helpful"],
                    details["further_support"],
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise MentorConflictError("Feedback has already been submitted.") from error
    feedback = get_feedback(booking_id, profile_id, db_path=db_path)
    if feedback is None:
        raise MentorNotFoundError("The feedback could not be loaded after saving.")
    return feedback


def get_feedback(
    booking_id: str,
    profile_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    profile_id = _clean_id(profile_id, "Profile")
    with get_database_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT f.*
            FROM mentor_feedback f
            JOIN mentor_bookings b ON b.booking_id = f.booking_id
            JOIN job_seekers p ON p.profile_id = b.profile_id
            WHERE f.booking_id = ? AND b.profile_id = ? AND p.owner_id = ?
            """,
            (
                booking_id,
                profile_id,
                normalize_owner_id(get_current_owner_id()),
            ),
        ).fetchone()
    return _feedback_from_row(row) if row else None
