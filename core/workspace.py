"""Owner context and workspace paths for the shared KaziMsaada AI database.

The web app uses one SQLite database for all signed-in users. Personal rows are
tagged with an opaque owner ID instead of creating a separate database per
person, because the mentor directory and booking records must remain shared.

The command-line application and existing local records use the owner ID
``local``. Tests can switch owners with :func:`owner_scope`.
"""

from __future__ import annotations

import hashlib
import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

from .config import CV_DIR

LOCAL_OWNER_ID = "local"
DELETED_OWNER_ID = "deleted"
MENTOR_DIRECTORY_OWNER_ID = "mentor-directory"

_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_CURRENT_OWNER: ContextVar[str | None] = ContextVar(
    "kazimsaada_current_owner",
    default=None,
)
_STRICT_OWNER = False


class WorkspaceOwnerNotSet(RuntimeError):
    """Raised in strict mode when personal data is touched before sign-in."""


def set_strict_owner_mode(strict: bool) -> bool:
    """Enable or disable fail-closed owner scoping; returns the previous value."""

    global _STRICT_OWNER
    previous = _STRICT_OWNER
    _STRICT_OWNER = bool(strict)
    return previous


def is_strict_owner_mode() -> bool:
    return _STRICT_OWNER


def clear_current_owner_id() -> None:
    """Forget the owner at the start of an authentication-sensitive run."""

    _CURRENT_OWNER.set(None)


def normalize_owner_id(owner_id: str | None) -> str:
    """Return a safe owner identifier or fall back to the local owner."""

    text = str(owner_id or "").strip()
    if not text:
        return LOCAL_OWNER_ID
    if not _OWNER_PATTERN.fullmatch(text):
        raise ValueError("The workspace owner identifier is not valid.")
    return text


def owner_id_from_identity(identity: str) -> str:
    """Create a stable, opaque owner ID from an OIDC subject or email."""

    text = str(identity or "").strip()
    if not text:
        raise ValueError("A signed-in identity is required.")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def get_current_owner_id() -> str:
    owner = _CURRENT_OWNER.get()
    if owner is not None:
        return normalize_owner_id(owner)
    if _STRICT_OWNER:
        raise WorkspaceOwnerNotSet(
            "No signed-in workspace owner is set; refusing to access personal data."
        )
    return LOCAL_OWNER_ID


def set_current_owner_id(owner_id: str | None) -> str:
    resolved = normalize_owner_id(owner_id)
    _CURRENT_OWNER.set(resolved)
    return resolved


@contextmanager
def owner_scope(owner_id: str | None) -> Iterator[str]:
    """Temporarily run a block as another owner (mainly for tests)."""

    token = _CURRENT_OWNER.set(normalize_owner_id(owner_id))
    try:
        yield _CURRENT_OWNER.get()
    finally:
        _CURRENT_OWNER.reset(token)


def is_local_owner(owner_id: str | None = None) -> bool:
    return (owner_id or get_current_owner_id()) == LOCAL_OWNER_ID


def current_cv_dir(owner_id: str | None = None) -> Path:
    """Return the CV folder for the current owner.

    Local mode keeps the original ``data/cvs`` folder so existing files remain
    visible. Signed-in owners get a private subfolder under ``data/cvs/users``.
    """

    owner = normalize_owner_id(owner_id or get_current_owner_id())
    if owner == LOCAL_OWNER_ID:
        return CV_DIR
    return CV_DIR / "users" / owner


__all__ = [
    "DELETED_OWNER_ID",
    "LOCAL_OWNER_ID",
    "MENTOR_DIRECTORY_OWNER_ID",
    "WorkspaceOwnerNotSet",
    "clear_current_owner_id",
    "current_cv_dir",
    "get_current_owner_id",
    "is_local_owner",
    "is_strict_owner_mode",
    "normalize_owner_id",
    "owner_id_from_identity",
    "owner_scope",
    "set_current_owner_id",
    "set_strict_owner_mode",
]
