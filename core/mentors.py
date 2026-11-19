"""Domain rules for the KaziMsaada AI Mentor Meeting Centre.

This module is intentionally independent of Streamlit and SQLite. It owns the
allowed statuses, input validation, Nairobi/UTC conversion, and presentation
rules used by the stores and interface.
"""

from __future__ import annotations

import re
import secrets
from datetime import date as date_cls
from datetime import datetime, time as time_cls
from datetime import timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    NAIROBI_TZ = ZoneInfo("Africa/Nairobi")
except ZoneInfoNotFoundError:  # pragma: no cover - Windows without tzdata
    # Nairobi has used UTC+3 without daylight saving since 1942.
    NAIROBI_TZ = timezone(timedelta(hours=3), "EAT")

UTC = timezone.utc

APPLICATION_PENDING = "pending"
APPLICATION_APPROVED = "approved"
APPLICATION_REJECTED = "rejected"
APPLICATION_STATUSES = (
    APPLICATION_PENDING,
    APPLICATION_APPROVED,
    APPLICATION_REJECTED,
)
APPLICATION_STATUS_LABELS = {
    APPLICATION_PENDING: "Pending review",
    APPLICATION_APPROVED: "Approved",
    APPLICATION_REJECTED: "Rejected",
}

BOOKING_PENDING = "pending"
BOOKING_CONFIRMED = "confirmed"
BOOKING_REJECTED = "rejected"
BOOKING_CANCELLED = "cancelled"
BOOKING_COMPLETED = "completed"
BOOKING_STATUSES = (
    BOOKING_PENDING,
    BOOKING_CONFIRMED,
    BOOKING_REJECTED,
    BOOKING_CANCELLED,
    BOOKING_COMPLETED,
)
BOOKING_STATUS_LABELS = {
    BOOKING_PENDING: "Awaiting mentor confirmation",
    BOOKING_CONFIRMED: "Confirmed",
    BOOKING_REJECTED: "Rejected",
    BOOKING_CANCELLED: "Cancelled",
    BOOKING_COMPLETED: "Completed",
}

AVAILABILITY_OPEN = "open"
AVAILABILITY_BOOKED = "booked"
AVAILABILITY_REMOVED = "removed"
AVAILABILITY_STATUSES = (
    AVAILABILITY_OPEN,
    AVAILABILITY_BOOKED,
    AVAILABILITY_REMOVED,
)

DURATION_OPTIONS = (30, 45, 60, 90)
DEFAULT_DURATION_OPTIONS = (30, 45, 60)

MAX_NAME_CHARS = 120
MAX_EMAIL_CHARS = 200
MAX_TITLE_CHARS = 140
MAX_INDUSTRY_CHARS = 100
MAX_SPECIALISATION_CHARS = 140
MAX_LIST_ITEM_CHARS = 100
MAX_EXPERIENCE_CHARS = 3000
MAX_BIOGRAPHY_CHARS = 4000
MAX_QUALIFICATIONS_CHARS = 3000
MAX_SUPPORTING_CHARS = 3000
MAX_PURPOSE_CHARS = 1200
MAX_TARGET_ROLE_CHARS = 160
MAX_FEEDBACK_CHARS = 1800
MAX_FURTHER_SUPPORT_CHARS = 1200
MAX_RESCHEDULE_CHARS = 1000
MAX_MEETING_URL_CHARS = 500
MAX_AVATAR_URL_CHARS = 500
MAX_SLOTS_PER_REQUEST = 20

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MentorError(Exception):
    """Base class for mentor-centre failures."""


class MentorValidationError(MentorError, ValueError):
    """Raised when mentor input fails validation."""


class MentorNotFoundError(MentorError, LookupError):
    """Raised when a mentor record cannot be found or is not public."""


class MentorConflictError(MentorError):
    """Raised when a booking, approval or feedback would be duplicated."""


class MentorPermissionError(MentorError, PermissionError):
    """Raised when an actor does not own the mentor record or booking."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_utc_iso(value: datetime) -> str:
    """Convert an aware datetime to a stable UTC ISO string."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=NAIROBI_TZ)
    return value.astimezone(UTC).isoformat(timespec="seconds")


def now_utc_iso() -> str:
    return to_utc_iso(utc_now())


def parse_utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError) as error:
            raise MentorValidationError("A meeting date or time is invalid.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def nairobi_to_utc(day: date_cls, start_time: time_cls) -> datetime:
    """Interpret a date/time entered in Nairobi time and return UTC."""

    local = datetime.combine(day, start_time).replace(tzinfo=NAIROBI_TZ)
    return local.astimezone(UTC)


def format_nairobi(value: str | datetime, *, include_weekday: bool = True) -> str:
    parsed = parse_utc(value).astimezone(NAIROBI_TZ)
    pattern = "%a %d %b %Y, %H:%M" if include_weekday else "%d %b %Y, %H:%M"
    return f"{parsed.strftime(pattern)} EAT"


def format_nairobi_date(value: str | datetime) -> str:
    return parse_utc(value).astimezone(NAIROBI_TZ).strftime("%d %b %Y")


def format_nairobi_time(value: str | datetime) -> str:
    return parse_utc(value).astimezone(NAIROBI_TZ).strftime("%H:%M")


def format_duration(minutes: int) -> str:
    minutes = int(minutes)
    if minutes < 60:
        return f"{minutes} min"
    hours, remainder = divmod(minutes, 60)
    if remainder:
        return f"{hours} hr {remainder} min"
    return f"{hours} hr"


def _clean_text(
    value,
    field_name: str,
    maximum: int,
    *,
    minimum: int = 1,
    required: bool = True,
) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise MentorValidationError(f"{field_name} is required.")
        return ""
    if len(text) < minimum:
        raise MentorValidationError(
            f"{field_name} must be at least {minimum} characters."
        )
    if len(text) > maximum:
        raise MentorValidationError(
            f"{field_name} must be {maximum} characters or fewer."
        )
    return text


def clean_email(value) -> str:
    email = _clean_text(value, "Email address", MAX_EMAIL_CHARS).lower()
    if not EMAIL_PATTERN.match(email):
        raise MentorValidationError("Enter a valid email address.")
    return email


def clean_list(
    value,
    field_name: str,
    *,
    maximum_items: int,
    maximum_item_chars: int = MAX_LIST_ITEM_CHARS,
    minimum_items: int = 1,
    required: bool = True,
) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\n,;]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    elif value is None:
        raw_items = []
    else:
        raw_items = [value]

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text:
            continue
        if len(text) > maximum_item_chars:
            raise MentorValidationError(
                f"Each {field_name.lower()} entry must be "
                f"{maximum_item_chars} characters or fewer."
            )
        key = text.casefold()
        if key not in seen:
            seen.add(key)
            cleaned.append(text)

    if required and len(cleaned) < minimum_items:
        raise MentorValidationError(
            f"Add at least {minimum_items} {field_name.lower()}."
        )
    if len(cleaned) > maximum_items:
        raise MentorValidationError(
            f"Add no more than {maximum_items} {field_name.lower()}."
        )
    return cleaned


def clean_duration_options(value) -> list[int]:
    if value in (None, ""):
        items = list(DEFAULT_DURATION_OPTIONS)
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
    else:
        items = list(value)

    cleaned: list[int] = []
    for item in items:
        try:
            minutes = int(item)
        except (TypeError, ValueError) as error:
            raise MentorValidationError("Choose valid session durations.") from error
        if minutes not in DURATION_OPTIONS:
            allowed = ", ".join(str(option) for option in DURATION_OPTIONS)
            raise MentorValidationError(
                f"Session durations must be one of: {allowed} minutes."
            )
        if minutes not in cleaned:
            cleaned.append(minutes)

    if not cleaned:
        raise MentorValidationError("Choose at least one session duration.")
    return sorted(cleaned)


def clean_https_url(
    value,
    field_name: str,
    *,
    maximum: int = MAX_MEETING_URL_CHARS,
    required: bool = True,
) -> str:
    text = _clean_text(
        value,
        field_name,
        maximum,
        required=required,
    )
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise MentorValidationError(
            f"{field_name} must be a complete https:// link."
        )
    if parsed.username or parsed.password:
        raise MentorValidationError(f"{field_name} must not contain a username or password.")
    if any(character.isspace() for character in text):
        raise MentorValidationError(f"{field_name} must not contain spaces.")
    return text


def validate_application(data: dict) -> dict:
    """Validate and normalise a mentor application."""

    if not isinstance(data, dict):
        raise MentorValidationError("The application details are invalid.")
    return {
        "full_name": _clean_text(data.get("full_name"), "Full name", MAX_NAME_CHARS),
        "email": clean_email(data.get("email")),
        "professional_title": _clean_text(
            data.get("professional_title"),
            "Professional title",
            MAX_TITLE_CHARS,
        ),
        "industry": _clean_text(
            data.get("industry"), "Industry", MAX_INDUSTRY_CHARS
        ),
        "specialisation": _clean_text(
            data.get("specialisation"),
            "Primary specialisation",
            MAX_SPECIALISATION_CHARS,
        ),
        "areas_of_expertise": clean_list(
            data.get("areas_of_expertise"),
            "Areas of expertise",
            maximum_items=15,
        ),
        "experience": _clean_text(
            data.get("experience"),
            "Professional experience",
            MAX_EXPERIENCE_CHARS,
            minimum=20,
        ),
        "biography": _clean_text(
            data.get("biography"),
            "Biography",
            MAX_BIOGRAPHY_CHARS,
            minimum=40,
        ),
        "qualifications": _clean_text(
            data.get("qualifications"),
            "Qualifications",
            MAX_QUALIFICATIONS_CHARS,
            minimum=5,
        ),
        "languages": clean_list(
            data.get("languages"),
            "Languages",
            maximum_items=10,
            maximum_item_chars=60,
        ),
        "supporting_info": _clean_text(
            data.get("supporting_info"),
            "Supporting information",
            MAX_SUPPORTING_CHARS,
            required=False,
        ),
        "avatar_url": clean_https_url(
            data.get("avatar_url"),
            "Profile image URL",
            maximum=MAX_AVATAR_URL_CHARS,
            required=False,
        ),
    }


def validate_mentor_profile(data: dict) -> dict:
    """Validate fields an approved mentor may update publicly."""

    if not isinstance(data, dict):
        raise MentorValidationError("The mentor profile details are invalid.")
    return {
        "full_name": _clean_text(data.get("full_name"), "Full name", MAX_NAME_CHARS),
        "professional_title": _clean_text(
            data.get("professional_title"),
            "Professional title",
            MAX_TITLE_CHARS,
        ),
        "biography": _clean_text(
            data.get("biography"),
            "Biography",
            MAX_BIOGRAPHY_CHARS,
            minimum=40,
        ),
        "industry": _clean_text(
            data.get("industry"), "Industry", MAX_INDUSTRY_CHARS
        ),
        "specialisation": _clean_text(
            data.get("specialisation"),
            "Specialisation",
            MAX_SPECIALISATION_CHARS,
        ),
        "experience": _clean_text(
            data.get("experience"),
            "Professional experience",
            MAX_EXPERIENCE_CHARS,
            minimum=20,
        ),
        "qualifications": _clean_text(
            data.get("qualifications"),
            "Qualifications",
            MAX_QUALIFICATIONS_CHARS,
            minimum=5,
        ),
        "languages": clean_list(
            data.get("languages"),
            "Languages",
            maximum_items=10,
            maximum_item_chars=60,
        ),
        "coaching_areas": clean_list(
            data.get("coaching_areas"),
            "Coaching areas",
            maximum_items=15,
        ),
        "duration_options": clean_duration_options(data.get("duration_options")),
        "avatar_url": clean_https_url(
            data.get("avatar_url"),
            "Profile image URL",
            maximum=MAX_AVATAR_URL_CHARS,
            required=False,
        ),
    }


def validate_booking_request(purpose, target_job_role="") -> dict:
    return {
        "purpose": _clean_text(
            purpose,
            "What you need help with",
            MAX_PURPOSE_CHARS,
            minimum=10,
        ),
        "target_job_role": _clean_text(
            target_job_role,
            "Target job role",
            MAX_TARGET_ROLE_CHARS,
            required=False,
        ),
    }


def validate_feedback(
    rating,
    comment="",
    helpful=True,
    further_support="",
) -> dict:
    try:
        rating_value = int(rating)
    except (TypeError, ValueError) as error:
        raise MentorValidationError("Choose a rating from 1 to 5.") from error
    if rating_value < 1 or rating_value > 5:
        raise MentorValidationError("Choose a rating from 1 to 5.")
    return {
        "rating": rating_value,
        "comment": _clean_text(
            comment,
            "Feedback",
            MAX_FEEDBACK_CHARS,
            required=False,
        ),
        "helpful": 1 if bool(helpful) else 0,
        "further_support": _clean_text(
            further_support,
            "Further support",
            MAX_FURTHER_SUPPORT_CHARS,
            required=False,
        ),
    }


def validate_reschedule_note(note) -> str:
    return _clean_text(
        note,
        "Reschedule request",
        MAX_RESCHEDULE_CHARS,
        minimum=3,
    )


def validate_review_note(note) -> str:
    return _clean_text(
        note,
        "Review note",
        1000,
        required=False,
    )


def validate_booking_reference(value) -> str:
    return _clean_text(value, "Booking reference", 40)


def new_booking_reference(now: datetime | None = None) -> str:
    stamp = (now or utc_now()).astimezone(NAIROBI_TZ).strftime("%Y%m%d")
    token = secrets.token_hex(4).upper()
    return f"KM-{stamp}-{token}"


def is_future(value: str | datetime) -> bool:
    return parse_utc(value) > utc_now()


def is_past(value: str | datetime) -> bool:
    return parse_utc(value) <= utc_now()


def initials(name: str) -> str:
    parts = [part for part in str(name or "").split() if part]
    if not parts:
        return "KM"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()
