"""Career profile data access and validation.

All SQL is parameterized. Functions raise ``sqlite3.Error`` on database
failures so the CLI and web layers can present context-appropriate messages.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .database import get_database_connection

PROFILE_FIELDS = (
    "name",
    "education",
    "location",
    "experience",
    "career_interest",
)

REQUIRED_FIELDS = {
    "name": "Full name",
    "education": "Education",
    "location": "Town or county",
    "career_interest": "Career or industry of interest",
}

MAX_LENGTHS = {
    "name": 120,
    "education": 300,
    "location": 120,
    "experience": 1000,
    "career_interest": 200,
}


class ProfileValidationError(ValueError):
    """Raised when profile data fails validation."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


class ProfileNotFoundError(LookupError):
    """Raised when a profile cannot be found after a write."""


def normalize_skills(skills) -> list[str]:
    """Return clean, unique skill names while preserving their order."""

    if isinstance(skills, str):
        skills = skills.split(",")

    if not isinstance(skills, (list, tuple)):
        return []

    cleaned: list[str] = []
    seen: set[str] = set()

    for skill in skills:
        text = str(skill).strip()
        if text and text.casefold() not in seen:
            cleaned.append(text)
            seen.add(text.casefold())

    return cleaned


def validate_profile(data: dict, *, require_experience: bool = True) -> dict[str, str]:
    """Validate profile fields and return a mapping of field -> message."""

    errors: dict[str, str] = {}

    for field, label in REQUIRED_FIELDS.items():
        value = str(data.get(field, "")).strip()
        if not value:
            errors[field] = f"{label} is required."

    if require_experience:
        value = str(data.get("experience", "")).strip()
        if not value:
            errors["experience"] = (
                "Describe your experience, or say you have no formal "
                "experience yet."
            )

    for field, maximum in MAX_LENGTHS.items():
        value = str(data.get(field, "")).strip()
        if len(value) > maximum:
            errors[field] = (
                f"Please keep this under {maximum} characters "
                f"({len(value)} used)."
            )

    skills = normalize_skills(data.get("skills", []))
    if len(skills) > 40:
        errors["skills"] = "Please list no more than 40 skills."
    for skill in skills:
        if len(skill) > 80:
            errors["skills"] = "Keep each skill under 80 characters."
            break

    return errors


def _row_to_profile(row: sqlite3.Row) -> dict:
    profile = dict(row)

    try:
        skills = json.loads(profile.get("skills") or "[]")
    except (json.JSONDecodeError, TypeError):
        skills = []

    profile["skills"] = skills if isinstance(skills, list) else []
    return profile


def _clean_profile(data: dict) -> dict:
    """Normalize editable profile values without touching identifiers."""

    cleaned = {field: str(data.get(field, "") or "").strip() for field in PROFILE_FIELDS}
    cleaned["experience"] = cleaned["experience"] or "No formal work experience yet"
    cleaned["skills"] = normalize_skills(data.get("skills", []))
    return cleaned


def load_profiles(db_path: str | Path | None = None) -> list[dict]:
    """Return every saved profile, newest first."""

    with get_database_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM job_seekers
            ORDER BY created_at DESC
            """
        ).fetchall()

    return [_row_to_profile(row) for row in rows]


def get_profile(
    profile_id: str,
    db_path: str | Path | None = None,
) -> dict | None:
    """Return one profile by its unique ID, or ``None``."""

    with get_database_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM job_seekers
            WHERE profile_id = ?
            """,
            (profile_id,),
        ).fetchone()

    return _row_to_profile(row) if row else None


def create_profile(
    data: dict,
    db_path: str | Path | None = None,
) -> dict:
    """Validate and insert a new profile, returning the stored record."""

    data = dict(data)
    if not str(data.get("experience", "") or "").strip():
        data["experience"] = "No formal work experience yet"

    errors = validate_profile(data)
    if errors:
        raise ProfileValidationError(errors)

    cleaned = _clean_profile(data)
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    profile = {
        "profile_id": str(uuid4()),
        "created_at": now,
        "updated_at": None,
        **cleaned,
    }

    with get_database_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO job_seekers (
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
                profile["profile_id"],
                profile["name"],
                profile["education"],
                profile["location"],
                profile["experience"],
                profile["career_interest"],
                json.dumps(profile["skills"], ensure_ascii=False),
                profile["created_at"],
                profile["updated_at"],
            ),
        )

    return profile


def save_profile_record(
    job_seeker: dict,
    db_path: str | Path | None = None,
) -> dict:
    """Insert a pre-built profile dictionary (used by the CLI).

    The record is verified inside the same transaction before returning.
    """

    with get_database_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO job_seekers (
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
                job_seeker["profile_id"],
                job_seeker["name"],
                job_seeker["education"],
                job_seeker["location"],
                job_seeker["experience"],
                job_seeker["career_interest"],
                json.dumps(job_seeker["skills"], ensure_ascii=False),
                job_seeker["created_at"],
                job_seeker.get("updated_at"),
            ),
        )

        saved = connection.execute(
            """
            SELECT *
            FROM job_seekers
            WHERE profile_id = ?
            """,
            (job_seeker["profile_id"],),
        ).fetchone()

    if saved is None:
        raise ProfileNotFoundError("The profile could not be found after saving.")

    return _row_to_profile(saved)


def update_profile_record(
    profile: dict,
    db_path: str | Path | None = None,
) -> bool:
    """Update an existing profile. Returns ``True`` when one row changed."""

    updated_at = profile.get("updated_at") or datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    with get_database_connection(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE job_seekers
            SET
                name = ?,
                education = ?,
                location = ?,
                experience = ?,
                career_interest = ?,
                skills = ?,
                updated_at = ?
            WHERE profile_id = ?
            """,
            (
                profile["name"],
                profile["education"],
                profile["location"],
                profile["experience"],
                profile["career_interest"],
                json.dumps(normalize_skills(profile.get("skills", [])), ensure_ascii=False),
                updated_at,
                profile["profile_id"],
            ),
        )

    return cursor.rowcount == 1


def delete_profile_record(
    profile_id: str,
    db_path: str | Path | None = None,
) -> bool:
    """Delete one profile by its unique ID."""

    with get_database_connection(db_path) as connection:
        cursor = connection.execute(
            """
            DELETE FROM job_seekers
            WHERE profile_id = ?
            """,
            (profile_id,),
        )

    return cursor.rowcount == 1


def search_profiles(
    query: str,
    db_path: str | Path | None = None,
) -> list[dict]:
    """Search by name substring or exact profile ID (CLI semantics)."""

    term = query.strip().casefold()
    if not term:
        return []

    matches = []
    for profile in load_profiles(db_path):
        name = str(profile.get("name", "")).casefold()
        profile_id = str(profile.get("profile_id", "")).casefold()
        if term in name or term == profile_id:
            matches.append(profile)

    return matches


def profile_completeness(profile: dict) -> int:
    """Return a simple, explainable completeness percentage (0-100)."""

    if not profile:
        return 0

    checks = [
        bool(str(profile.get("name", "")).strip()),
        bool(str(profile.get("education", "")).strip()),
        bool(str(profile.get("location", "")).strip()),
        bool(str(profile.get("experience", "")).strip()),
        bool(str(profile.get("career_interest", "")).strip()),
        len(profile.get("skills", [])) >= 3,
    ]

    return round(100 * sum(checks) / len(checks))
