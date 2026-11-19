"""Access-code helpers for mentor and administrator workspaces.

Mentor access codes are generated once when an application is approved. Only a
PBKDF2 hash is stored in SQLite; the raw code is shown to the administrator
once and must be shared with the mentor privately.

The application currently has no user authentication. The administrator gate
therefore reads a strong code from Streamlit secrets rather than treating the
active profile selector as a security boundary. This is still not a substitute
for real sign-in, email verification, and role-based access control.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets as pysecrets
from typing import Mapping

ACCESS_CODE_PREFIX = "KM-MENTOR-"
HASH_ALGORITHM = "pbkdf2_sha256"
HASH_ITERATIONS = 240_000
ADMIN_SECRET_SECTION = "mentor_admin"


def generate_access_code() -> str:
    """Return a high-entropy mentor access code."""

    return f"{ACCESS_CODE_PREFIX}{pysecrets.token_urlsafe(24)}"


def hash_access_code(code: str) -> str:
    """Hash an access code for storage. The raw code is never stored."""

    value = str(code or "")
    if not value:
        raise ValueError("An access code is required.")
    salt = pysecrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        salt.encode("ascii"),
        HASH_ITERATIONS,
    ).hex()
    return f"{HASH_ALGORITHM}${HASH_ITERATIONS}${salt}${digest}"


def verify_access_code(code: str, encoded_hash: str) -> bool:
    """Verify a raw access code against a stored hash."""

    try:
        algorithm, iterations_text, salt, expected = str(encoded_hash).split("$", 3)
        iterations = int(iterations_text)
    except (AttributeError, TypeError, ValueError):
        return False
    if algorithm != HASH_ALGORITHM or iterations <= 0:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        str(code or "").encode("utf-8"),
        salt.encode("ascii"),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate, expected)


def admin_access_configured(section: Mapping | None) -> bool:
    if not isinstance(section, Mapping):
        return False
    return bool(
        str(section.get("access_code_hash") or "").strip()
        or str(section.get("access_code") or "").strip()
    )


def verify_admin_access(code: str, section: Mapping | None) -> bool:
    """Check an administrator code from Streamlit secrets.

    ``access_code_hash`` is preferred. A plain ``access_code`` is accepted for
    convenience because Streamlit secrets are already protected, but hashing is
    documented as the stronger option.
    """

    if not isinstance(section, Mapping):
        return False
    stored_hash = str(section.get("access_code_hash") or "").strip()
    if stored_hash:
        return verify_access_code(code, stored_hash)
    stored_code = str(section.get("access_code") or "").strip()
    if not stored_code:
        return False
    return hmac.compare_digest(str(code or "").strip(), stored_code)
