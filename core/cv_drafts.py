"""Persistent CV drafts, scoped to the active workspace owner."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .database import get_database_connection
from .workspace import get_current_owner_id, normalize_owner_id

MAX_DRAFT_JSON_CHARS = 200_000


class CvDraftError(Exception):
    """Raised when a CV draft cannot be saved or loaded."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _require_owned_profile(
    connection: sqlite3.Connection,
    profile_id: str,
    owner_id: str,
) -> None:
    row = connection.execute(
        "SELECT 1 FROM job_seekers WHERE profile_id = ? AND owner_id = ?",
        (profile_id, owner_id),
    ).fetchone()
    if row is None:
        raise CvDraftError("The active profile could not be found.")


def load_cv_draft(
    profile_id: str,
    db_path: str | Path | None = None,
    *,
    owner_id: str | None = None,
) -> dict[str, Any]:
    """Return the saved draft for this profile and owner, or an empty dict."""

    owner = normalize_owner_id(owner_id or get_current_owner_id())
    with get_database_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT draft_json
            FROM cv_drafts
            WHERE profile_id = ? AND owner_id = ?
            """,
            (str(profile_id), owner),
        ).fetchone()

    if row is None:
        return {}

    try:
        draft = json.loads(row["draft_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return draft if isinstance(draft, dict) else {}


def load_cv_draft_updated_at(
    profile_id: str,
    db_path: str | Path | None = None,
    *,
    owner_id: str | None = None,
) -> str | None:
    """Return when this profile's draft was last autosaved, if known."""

    owner = normalize_owner_id(owner_id or get_current_owner_id())
    with get_database_connection(db_path) as connection:
        row = connection.execute(
            "SELECT updated_at FROM cv_drafts WHERE profile_id = ? AND owner_id = ?",
            (str(profile_id), owner),
        ).fetchone()
    return str(row["updated_at"]) if row else None


def save_cv_draft(
    profile_id: str,
    draft: dict[str, Any],
    db_path: str | Path | None = None,
    *,
    owner_id: str | None = None,
) -> None:
    """Create or update the autosaved draft for this profile."""

    if not isinstance(draft, dict):
        raise CvDraftError("The CV draft is not valid.")

    try:
        payload = json.dumps(draft, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as error:
        raise CvDraftError("The CV draft could not be serialised.") from error

    if len(payload) > MAX_DRAFT_JSON_CHARS:
        raise CvDraftError(
            "This CV draft is too large to autosave. Remove some long text and try again."
        )

    owner = normalize_owner_id(owner_id or get_current_owner_id())
    now = _now()

    with get_database_connection(db_path) as connection:
        _require_owned_profile(connection, str(profile_id), owner)
        connection.execute(
            """
            INSERT INTO cv_drafts (
                profile_id,
                owner_id,
                draft_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                owner_id = excluded.owner_id,
                draft_json = excluded.draft_json,
                updated_at = excluded.updated_at
            """,
            (str(profile_id), owner, payload, now, now),
        )


def delete_cv_draft(
    profile_id: str,
    db_path: str | Path | None = None,
    *,
    owner_id: str | None = None,
) -> bool:
    owner = normalize_owner_id(owner_id or get_current_owner_id())
    with get_database_connection(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM cv_drafts WHERE profile_id = ? AND owner_id = ?",
            (str(profile_id), owner),
        )
    return cursor.rowcount == 1


__all__ = [
    "CvDraftError",
    "delete_cv_draft",
    "load_cv_draft",
    "load_cv_draft_updated_at",
    "save_cv_draft",
]
