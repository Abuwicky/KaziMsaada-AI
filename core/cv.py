"""CV content building, preview rendering, and PDF generation.

One structured document drives every output:

    profile + cv_data ──► build_cv_document() ──┬─► build_cv_content()  canonical text (.txt)
                                                ├─► build_cv_html()     live preview
                                                └─► generate_cv_pdf()   downloadable PDF

Templates are plain configuration (see ``TEMPLATES``). Adding a template means
adding one dictionary entry: layout, header style, heading style, skills style,
fonts, density, colours and section order are all read from that entry by both
the HTML and the PDF renderer, so the preview and the PDF cannot drift apart.

Public API kept from the previous version:
    TEMPLATES, DEFAULT_TEMPLATE, build_cv_content, build_cv_html,
    generate_cv_pdf, save_cv_bundle, list_saved_cvs, count_saved_cvs,
    validate_cv_contact_details, is_valid_email, is_valid_phone,
    phone_digit_count, add_cv_section, add_work_experience_section
"""

from __future__ import annotations

import html
import io
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    FrameBreak,
    HRFlowable,
    KeepInFrame,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .config import CV_DIR
from .profiles import normalize_skills

# Small branded footer printed on every PDF page. Set to "" to hide it.
BRAND_FOOTER = "Created with KaziMsaada AI"

SECTION_TITLES = {
    "summary": "Professional Summary",
    "education": "Education",
    "experience": "Work Experience",
    "projects": "Projects and Practical Experience",
    "volunteering": "Volunteering",
    "skills": "Skills",
    "certifications": "Certifications and Training",
    "languages": "Languages",
    "referees": "Referees",
}
DEFAULT_SECTION_ORDER = tuple(SECTION_TITLES)

# Page metrics shared by the PDF (points / mm) and the HTML preview.
_DENSITY = {
    "compact": {"body": 8.8, "lead": 11.8, "h2": 9.6, "h1": 19, "small": 8.0,
                "gap": 7.5, "para": 2.2, "side_mm": 15, "top_mm": 13, "bottom_mm": 16},
    "normal": {"body": 9.5, "lead": 13.2, "h2": 10.5, "h1": 21, "small": 8.8,
               "gap": 11, "para": 3.2, "side_mm": 19, "top_mm": 17, "bottom_mm": 18},
    "airy": {"body": 10.0, "lead": 14.6, "h2": 11, "h1": 24, "small": 9.2,
             "gap": 15, "para": 4.0, "side_mm": 21, "top_mm": 20, "bottom_mm": 20},
}

_FONTS = {  # regular, bold, italic (ReportLab built-in fonts, no files needed)
    "sans": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique"),
    "serif": ("Times-Roman", "Times-Bold", "Times-Italic"),
    "mono": ("Courier", "Courier-Bold", "Courier-Oblique"),
}
_CSS_FONTS = {
    "sans": 'Helvetica, "Helvetica Neue", Arial, "Liberation Sans", sans-serif',
    "serif": '"Times New Roman", Times, "Liberation Serif", serif',
    "mono": '"Courier New", Courier, "Liberation Mono", monospace',
}

_BASE_TEMPLATE = {
    "layout": "single",          # single | sidebar
    "header": "left",            # left | center
    "header_rule": None,         # None | thin | thick | double
    "band": False,               # full-width coloured header on page one
    "name_case": "upper",        # upper | as_typed
    "name_pt": None,             # override the density's name size
    "heading_style": "rule_light",  # rule_light | rule_accent | plain | bar | filled
    "skills_style": "bullets",   # bullets | columns | inline | chips
    "skills_cols": 2,
    "skills_sep": " · ",
    "font": "sans",              # sans | serif | mono
    "heading_font": None,        # defaults to ``font``
    "density": "normal",         # compact | normal | airy
    "sidebar": (),               # section keys placed in the sidebar column
    "section_order": DEFAULT_SECTION_ORDER,
    "ink": "#222222",
    "ats": "Best",               # Best | Good | Use with care (for badges in the UI)
    "best_for": "",
}


def _template(**options) -> dict:
    return {**_BASE_TEMPLATE, **options}


# Keys 'name', 'description', 'accent' and 'muted' are read by other pages
# (template picker, settings swatches); everything else is rendering config.
TEMPLATES = {
    "classic": _template(
        name="Classic Professional",
        description="A clean, traditional, single-column layout.",
        best_for="Most applications and traditional employers",
        accent="#17365D", muted="#526273",
        header="center", header_rule="thin",
        heading_style="rule_light", skills_style="columns", skills_cols=2,
    ),
    "modern": _template(
        name="Modern Professional",
        description="A contemporary layout with a strong colour accent.",
        best_for="Corporate, NGO and private-sector roles",
        accent="#087E8B", muted="#425466",
        header="left", header_rule="thick", name_pt=23,
        heading_style="rule_accent", skills_style="chips", ats="Good",
    ),
    "graduate": _template(
        name="Graduate and Early-Career",
        description="Highlights education, skills, and practical projects.",
        best_for="First job, internships and attachments",
        accent="#315C42", muted="#52665A",
        header="center", header_rule="thin",
        heading_style="rule_light", skills_style="inline",
        section_order=("summary", "education", "skills", "projects", "experience",
                       "volunteering", "certifications", "languages", "referees"),
    ),
    "ats_plain": _template(
        name="ATS Plain",
        description="Plain single column, no colour or graphics, built for online application systems.",
        best_for="Online portals and large employers",
        accent="#1A1A1A", muted="#444444", ink="#111111",
        header="left", name_case="as_typed", name_pt=20,
        heading_style="plain", skills_style="inline", skills_sep=", ",
        section_order=("summary", "skills", "experience", "education", "projects",
                       "certifications", "volunteering", "languages", "referees"),
    ),
    "sidebar": _template(
        name="Sidebar",
        description="Two columns: a coloured side panel for contact, skills and languages.",
        best_for="Standing out in print or when emailing a CV directly",
        accent="#24566F", muted="#4A5C68",
        layout="sidebar", sidebar=("skills", "languages", "certifications"),
        header="left", name_case="as_typed", name_pt=24,
        heading_style="rule_accent", ats="Use with care",
        section_order=("summary", "experience", "education", "projects",
                       "volunteering", "skills", "certifications", "languages", "referees"),
    ),
    "executive": _template(
        name="Executive",
        description="Spacious serif layout with a strong summary and experience first.",
        best_for="Senior, supervisory and management roles",
        accent="#6B1E2E", muted="#5C4A4E",
        font="serif", density="airy", name_case="as_typed", name_pt=26,
        header="left", header_rule="double",
        heading_style="rule_light", skills_style="inline",
        section_order=("summary", "experience", "education", "skills", "certifications",
                       "volunteering", "projects", "languages", "referees"),
    ),
    "compact": _template(
        name="Compact One-Page",
        description="Tighter spacing so more fits on a single page.",
        best_for="Experienced applicants with a lot to include",
        accent="#2F4858", muted="#55636E",
        density="compact", name_pt=19, header="left", header_rule="thin",
        heading_style="rule_light", skills_style="inline", skills_sep=", ",
    ),
    "skills_first": _template(
        name="Skills First",
        description="Leads with skills and shows them as tags before your experience.",
        best_for="Career changers and people with limited formal experience",
        accent="#B4530A", muted="#6B5A4E",
        header="left", header_rule="thin", name_case="as_typed", name_pt=23,
        heading_style="bar", skills_style="chips", ats="Good",
        section_order=("summary", "skills", "experience", "projects", "education",
                       "volunteering", "certifications", "languages", "referees"),
    ),
    "creative": _template(
        name="Creative Band",
        description="A bold coloured header band with shaded section titles.",
        best_for="Design, media, marketing and creative roles",
        accent="#5B21B6", muted="#5B5675",
        band=True, header="left", name_case="as_typed", name_pt=26,
        heading_style="filled", skills_style="chips", ats="Good",
    ),
    "technical": _template(
        name="Technical",
        description="Skills, projects and certifications up front, with a monospaced heading style.",
        best_for="IT, engineering and other technical roles",
        accent="#1D4ED8", muted="#475569",
        heading_font="mono", header="left", header_rule="thin", name_case="as_typed",
        heading_style="rule_accent", skills_style="columns", skills_cols=3, ats="Good",
        section_order=("summary", "skills", "projects", "experience", "certifications",
                       "education", "volunteering", "languages", "referees"),
    ),
}

DEFAULT_TEMPLATE = "classic"

_EMAIL_LOCAL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
_EMAIL_DOMAIN_LABEL_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


# --------------------------------------------------------------------------
# Input cleaning and validation
# --------------------------------------------------------------------------

def _clean_items(value) -> list[str]:
    """Return a clean list from a list-like value or multiline text.

    Older drafts and CLI callers may pass a single string where the newer UI
    passes a list. Handling both here keeps the CV data contract backward
    compatible without duplicating logic in the interface.
    """

    if value is None:
        return []

    if isinstance(value, str):
        raw_items: Iterable = value.replace(";", "\n").splitlines()
    elif isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = [value]

    return [str(item).strip() for item in raw_items if str(item).strip()]


def is_valid_email(value: str) -> bool:
    """Apply practical email checks without rejecting normal business addresses."""

    text = str(value or "").strip()
    if len(text) > 254 or text.count("@") != 1:
        return False

    local, domain = text.rsplit("@", 1)
    if not local or not domain or len(local) > 64:
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    if not _EMAIL_LOCAL_RE.fullmatch(local):
        return False

    labels = domain.split(".")
    if len(labels) < 2 or any(not label for label in labels):
        return False
    if any(not _EMAIL_DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
        return False

    # A one-character top-level domain is not a usable public address.
    return len(labels[-1]) >= 2


def phone_digit_count(value: str) -> int:
    """Count digits so spaces, plus signs and hyphens do not affect validation."""

    return sum(1 for character in str(value or "") if character.isdigit())


def is_valid_phone(value: str) -> bool:
    return phone_digit_count(value) >= 7


def validate_cv_contact_details(
    target_role: str,
    email: str,
    phone: str,
) -> dict[str, str]:
    """Return field-specific messages for the CV download/save requirements."""

    errors: dict[str, str] = {}
    if not str(target_role or "").strip():
        errors["target_role"] = "Enter the target job position."

    if not is_valid_email(email):
        errors["email"] = (
            "Enter a complete email address with @ and a dot after it, "
            "for example name@example.com."
        )

    if not is_valid_phone(phone):
        errors["phone"] = "Enter a phone number with at least 7 digits."

    return errors


# --------------------------------------------------------------------------
# Structured document
# --------------------------------------------------------------------------

def _date_range(experience: dict) -> str:
    return (
        f"{experience.get('start_date', '')} - "
        f"{experience.get('end_date', '')}"
    ).strip(" -")


def _entry_dates(entry: dict) -> str:
    """Display form of an experience's dates (en dash between the two ends)."""

    return str(entry.get("dates") or _date_range(entry)).replace(" - ", " – ")


def _empty_document() -> dict:
    return {
        "name": "", "location": "", "phone": "", "email": "",
        "target_role": "", "summary": "",
        "education": [], "experience": [], "projects": [], "volunteering": [],
        "skills": [], "certifications": [], "languages": [], "referees": [],
    }


def _experience_entries(items) -> list[dict]:
    entries = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("job_title", "")).strip()
        organisation = str(item.get("organisation", "")).strip()
        if not (title or organisation):
            continue
        entries.append({
            "job_title": title,
            "organisation": organisation,
            "location": str(item.get("location", "")).strip(),
            "start_date": str(item.get("start_date", "")).strip(),
            "end_date": str(item.get("end_date", "")).strip(),
            "responsibilities": _clean_items(item.get("responsibilities", [])),
        })
    return entries


def build_cv_document(profile: dict, cv_data: dict | None = None) -> dict:
    """Merge a profile and the CV form data into one clean, render-ready dict."""

    cv_data = cv_data or {}

    skills = cv_data.get("skills")
    if skills is None:
        skills = profile.get("skills", [])

    primary_education = [
        line.strip()
        for line in str(profile.get("education", "") or "").splitlines()
        if line.strip()
    ]

    document = _empty_document()
    document.update({
        "name": str(profile.get("name", "")).strip(),
        "location": str(profile.get("location", "")).strip(),
        "phone": str(cv_data.get("phone", "")).strip(),
        "email": str(cv_data.get("email", "")).strip(),
        "target_role": str(cv_data.get("target_role", "")).strip(),
        "summary": str(cv_data.get("summary", "")).strip(),
        "education": primary_education + _clean_items(cv_data.get("education", [])),
        "experience": _experience_entries(cv_data.get("experience", [])),
        "projects": _clean_items(cv_data.get("projects", [])),
        "volunteering": _clean_items(cv_data.get("volunteering", [])),
        "skills": normalize_skills(skills),
        "certifications": _clean_items(cv_data.get("certifications", [])),
        "languages": _clean_items(cv_data.get("languages", [])),
        "referees": _clean_items(cv_data.get("referees", [])),
    })
    return document


# --------------------------------------------------------------------------
# Canonical text CV
# --------------------------------------------------------------------------

def add_cv_section(lines: list[str], heading: str, items: Iterable[str]) -> None:
    """Append a bulleted CV section when information is available."""

    items = _clean_items(items)
    if not items:
        return

    lines.append("")
    lines.append(heading.upper())
    lines.append("-" * 55)

    for item in items:
        lines.append(f"- {item}")


def add_work_experience_section(
    lines: list[str],
    experiences: Iterable[dict],
) -> None:
    """Append structured work experience using the original CLI format."""

    experiences = list(experiences)
    if not experiences:
        return

    lines.extend(["", "WORK EXPERIENCE", "-" * 55])

    for experience in experiences:
        lines.append("")
        title = str(experience.get("job_title", "")).strip()
        organisation = str(experience.get("organisation", "")).strip()
        if title:
            lines.append(title.upper())
        if organisation:
            lines.append(organisation)

        if experience.get("location"):
            lines.append(str(experience["location"]))

        date_range = _date_range(experience)
        if date_range:
            lines.append(date_range)

        for responsibility in _clean_items(experience.get("responsibilities", [])):
            lines.append(f"- {responsibility}")


class CVText(str):
    """The canonical CV text. It also carries the structured ``document`` it came
    from, so the PDF renderer can use real data instead of re-reading the text."""

    document: dict | None

    def __new__(cls, text: str, document: dict | None = None):
        instance = super().__new__(cls, text)
        instance.document = document
        return instance


def _render_text(document: dict) -> str:
    lines: list[str] = ["=" * 60, document["name"].upper(), "=" * 60]

    for label, key in (
        ("Location", "location"),
        ("Phone", "phone"),
        ("Email", "email"),
        ("Target Position", "target_role"),
    ):
        if document[key]:
            lines.append(f"{label}: {document[key]}")

    if document["summary"]:
        lines.extend(["", "PROFESSIONAL SUMMARY", "-" * 55, document["summary"]])

    add_cv_section(lines, SECTION_TITLES["education"], document["education"])
    add_work_experience_section(lines, document["experience"])
    for key in ("projects", "volunteering", "skills", "certifications",
                "languages", "referees"):
        add_cv_section(lines, SECTION_TITLES[key], document[key])

    lines.extend(["", "=" * 60, "CV CREATED WITH KAZIMSAADA AI", "=" * 60])
    return "\n".join(lines)


def build_cv_content(profile: dict, cv_data: dict | None = None) -> CVText:
    """Build the canonical CV text used by the CLI and PDF generator."""

    document = build_cv_document(profile, cv_data)
    return CVText(_render_text(document), document)


_HEADING_TO_KEY = {title.upper(): key for key, title in SECTION_TITLES.items()}
_CONTACT_PREFIXES = {
    "location:": "location",
    "phone:": "phone",
    "email:": "email",
    "target position:": "target_role",
}


def _is_rule(line: str, char: str) -> bool:
    text = line.strip()
    return len(text) >= 5 and set(text) == {char}


def _strip_bullet(line: str) -> str:
    text = line.strip()
    return text[2:].strip() if text.startswith("- ") else text


def _parse_experience_block(lines: list[str]) -> list[dict]:
    groups, current = [], []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    entries = []
    for group in groups:
        header = [line for line in group if not line.startswith("- ")]
        bullets = [line[2:].strip() for line in group if line.startswith("- ")]
        if not header:
            continue
        rest = header[2:]
        location = dates = ""
        if len(rest) >= 2:
            location, dates = rest[0], rest[1]
        elif len(rest) == 1:
            if re.search(r"\d|present|current|ongoing", rest[0], re.IGNORECASE):
                dates = rest[0]
            else:
                location = rest[0]
        entries.append({
            "job_title": header[0],
            "organisation": header[1] if len(header) > 1 else "",
            "location": location,
            "start_date": "",
            "end_date": "",
            "dates": dates,
            "responsibilities": bullets,
        })
    return entries


def parse_cv_text(text: str) -> dict:
    """Rebuild the structured document from canonical CV text.

    Only used when ``generate_cv_pdf`` is handed a plain string (for example
    text read back from a saved .txt file or from the command-line app).
    Job titles come back upper-case because the text form upper-cases them.
    """

    raw = str(text or "").splitlines()
    document = _empty_document()
    index, count = 0, len(raw)

    while index < count and (not raw[index].strip() or _is_rule(raw[index], "=")):
        index += 1
    if index < count:
        document["name"] = raw[index].strip()
        index += 1
    if index < count and _is_rule(raw[index], "="):
        index += 1

    sections: dict[str, list[str]] = {}
    current = None
    while index < count:
        line = raw[index].strip()
        following = raw[index + 1] if index + 1 < count else ""

        lowered = line.lower()
        prefix = next((p for p in _CONTACT_PREFIXES if lowered.startswith(p)), None)

        if current is None and prefix:
            document[_CONTACT_PREFIXES[prefix]] = line[len(prefix):].strip()
        elif line.upper() in _HEADING_TO_KEY and _is_rule(following, "-"):
            current = _HEADING_TO_KEY[line.upper()]
            sections[current] = []
            index += 1  # skip the dashed rule
        elif _is_rule(line, "="):
            break  # closing banner
        elif current is not None:
            sections[current].append(raw[index])
        index += 1

    for key, body in sections.items():
        if key == "summary":
            document["summary"] = " ".join(l.strip() for l in body if l.strip())
        elif key == "experience":
            document["experience"] = _parse_experience_block(body)
        else:
            document[key] = [_strip_bullet(l) for l in body if l.strip()]
    return document


def _coerce_document(cv_content) -> dict:
    if isinstance(cv_content, dict):
        return {**_empty_document(), **cv_content}
    document = getattr(cv_content, "document", None)
    if isinstance(document, dict):
        return document
    return parse_cv_text(str(cv_content or ""))


# --------------------------------------------------------------------------
# Theme helpers (colour maths, resolved template configuration)
# --------------------------------------------------------------------------

_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _normalise_hex(value) -> str | None:
    text = str(value or "").strip()
    return "#" + text.lstrip("#").upper() if _HEX_RE.match(text) else None


def _rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _to_hex(channels) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(c))) for c in channels)


def _mix(base: str, other: str, amount: float) -> str:
    """Blend ``amount`` (0-1) of ``other`` into ``base``."""

    return _to_hex(a + (b - a) * amount for a, b in zip(_rgb(base), _rgb(other)))


def _luminance(value: str) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _on_color(background: str) -> str:
    return "#FFFFFF" if _luminance(background) < 0.179 else "#111111"


def _readable(color: str, background: str = "#FFFFFF", minimum: float = 4.5) -> str:
    """Darken ``color`` until it can be read on ``background``."""

    result = color
    for _ in range(12):
        if _contrast(result, background) >= minimum:
            break
        result = _mix(result, "#000000", 0.15)
    return result


def _theme(template: str, accent: str | None = None) -> dict:
    """Resolve a template key (and optional accent override) into a full theme."""

    key = template if template in TEMPLATES else DEFAULT_TEMPLATE
    theme = dict(TEMPLATES[key])
    custom = _normalise_hex(accent)
    if custom:
        theme["accent"] = custom

    theme["key"] = key
    theme["m"] = dict(_DENSITY[theme["density"]])
    theme["accent_text"] = _readable(theme["accent"])
    theme["tint"] = _mix(theme["accent"], "#FFFFFF", 0.88)
    theme["on_accent"] = _on_color(theme["accent"])
    theme["side_rule"] = _mix(theme["accent"], theme["on_accent"], 0.45)
    theme["side_muted"] = _mix(theme["accent"], theme["on_accent"], 0.78)
    theme["font_body"] = _FONTS[theme["font"]]
    theme["font_head"] = _FONTS[theme["heading_font"] or theme["font"]]
    theme["name_size"] = theme["name_pt"] or theme["m"]["h1"]
    return theme


def _section_keys(document: dict, theme: dict) -> list[str]:
    order = list(theme["section_order"])
    order += [key for key in DEFAULT_SECTION_ORDER if key not in order]
    return [key for key in order if document.get(key)]


def _split_columns(document: dict, theme: dict) -> tuple[list[str], list[str]]:
    keys = _section_keys(document, theme)
    side = [key for key in keys if key in theme["sidebar"]]
    main = [key for key in keys if key not in theme["sidebar"]]
    return side, main


def _display_name(document: dict, theme: dict) -> str:
    name = document["name"].strip()
    return name.upper() if theme["name_case"] == "upper" else name


def _contact_items(document: dict) -> list[tuple[str, str]]:
    items = (
        ("Location", document["location"]),
        ("Phone", document["phone"]),
        ("Email", document["email"]),
    )
    return [(label, value) for label, value in items if value]


def _entry_lines(entry: dict) -> tuple[str, str]:
    title, organisation, place = (
        entry.get("job_title", ""), entry.get("organisation", ""), entry.get("location", "")
    )
    if title:
        return title, " · ".join(part for part in (organisation, place) if part)
    return organisation, place


# --------------------------------------------------------------------------
# HTML live preview
#
# The sheet is laid out in "A4 pixels" (794 px wide) and scaled with container
# query units, so the preview keeps the PDF's proportions at any column width.
# --------------------------------------------------------------------------

_HTML_FIXED_CSS = """
*{box-sizing:border-box}
html,body{margin:0}
body{padding:14px;background:#eef2f7}
.stage{container-type:inline-size;width:100%}
.sheet{--px:.75px}
@supports (width:1cqw){.sheet{--px:calc(100cqw / 794)}}
"""

_HTML_PAGE_CSS = r"""
.sheet{position:relative;width:100%;min-height:1123px;display:flex;flex-direction:column;
  background:#fff;color:@ink@;font-family:@fb@;font-size:@body@px;line-height:@lead@;
  box-shadow:0 10px 30px rgba(11,31,58,.14);overflow:hidden;overflow-wrap:break-word}
.sheet.side{flex-direction:row}
.sheet *{box-sizing:border-box}
.sheet h1,.sheet h2,.sheet p,.sheet ul{margin:0;padding:0}
.sheet ul{list-style:none}
.head{padding:@top@px @side@px 0}
.head-in{padding-bottom:7px}
.head.center{text-align:center}
.head.rule-thin .head-in{border-bottom:1px solid @accent@}
.head.rule-thick .head-in{border-bottom:2.2px solid @accent@}
.head.rule-double .head-in{border-bottom:3px double @accent@}
.head h1{font-family:@fh@;font-size:@name@px;line-height:1.18;color:@atext@;font-weight:700}
.head .role{font-size:@role@px;line-height:1.3;color:@muted@;font-weight:700;margin-top:2px}
.head .contact{font-size:@small@px;line-height:1.45;color:@muted@;margin-top:3px}
.head .contact i{font-style:normal;padding:0 4px;opacity:.55}
.head.band{background:@accent@;padding:@bandtop@px @side@px @bandbot@px}
.head.band .head-in{padding:0;border:0}
.head.band h1,.head.band .role,.head.band .contact{color:@on@}
.body{flex:1;display:flex;flex-direction:column;padding:0 @side@px @bottom@px}
.sec{margin-top:@gap@px}
.sec h2{font-family:@fh@;font-size:@h2@px;line-height:1.3;color:@atext@;font-weight:700}
.hs-rule_light .sec h2{border-bottom:1px solid #d8dfe8;padding-bottom:1.5px;margin-bottom:4px}
.hs-rule_accent .sec h2{border-bottom:1px solid @accent@;padding-bottom:1.5px;margin-bottom:4px}
.hs-plain .sec h2{margin-bottom:3px}
.hs-bar .sec h2{border-left:3.2px solid @accent@;padding:1.5px 0 1.5px 6px;margin-bottom:4px}
.hs-filled .sec h2{background:@tint@;border-left:2.5px solid @accent@;padding:3px 6px;margin-bottom:4px}
.sec p{margin:0 0 @para@px}
.b li{position:relative;padding-left:10px;margin:0 0 @para7@px}
.b li::before{content:"\2022";position:absolute;left:0}
.b.cols{column-count:2;column-gap:10px}
.b.cols.c3{column-count:3}
.b.cols li{break-inside:avoid}
.entry{margin-top:@gap2@px}
.sec h2 + .entry{margin-top:0}
.e-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.e-title{font-weight:700}
.e-date{font-size:@small@px;color:@muted@;white-space:nowrap}
.e-sub{font-style:italic;color:@muted@;margin-bottom:1.5px}
.chips{display:flex;flex-wrap:wrap;gap:4px}
.chip{background:@tint@;color:@atext@;border-radius:999px;padding:2.8px 5.5px;font-size:@chip@px;line-height:1.2}
.foot{margin-top:auto;padding-top:14px;font-size:7.5px;color:#8a97a6;display:flex;justify-content:space-between}
.empty-note{color:#8a97a6;font-style:italic;margin-top:26px}
.side-col{flex:none;width:234px;background:@accent@;color:@on@;padding:@top@px 26px @bottom@px}
.side-col .sec:first-child{margin-top:0}
.side-col .sec h2{color:@on@;background:none;border:0;border-bottom:1px solid @side_rule@;
  padding:0 0 1.5px;margin-bottom:4px;font-size:@sh2@px}
.side-col .b li::before{color:@side_muted@}
.side-col .ct li{padding-left:0;margin:0 0 4px}
.side-col .ct li::before{content:none}
.side-col .ct b{display:block;font-size:@label@px;line-height:1.3;color:@side_muted@;text-transform:uppercase;font-weight:700}
.side-col .ct span{overflow-wrap:anywhere}
.main-col{flex:1;min-width:0;display:flex;flex-direction:column;padding:0 57px @bottom@px 34px}
.main-col .head{padding:@top@px 0 0}
"""

_PX_RE = re.compile(r"(?<![\w.#-])(-?\d+(?:\.\d+)?)px\b")


def _to_scaled_px(css: str) -> str:
    return _PX_RE.sub(lambda match: f"calc({match.group(1)} * var(--px))", css)


def _pt_px(points: float) -> str:
    return f"{points * 4 / 3:.2f}"


def _mm_px(millimetres: float) -> str:
    return f"{millimetres * 96 / 25.4:.2f}"


def _html_css(theme: dict) -> str:
    m = theme["m"]
    tokens = {
        "ink": theme["ink"], "accent": theme["accent"], "atext": theme["accent_text"],
        "muted": theme["muted"], "tint": theme["tint"], "on": theme["on_accent"],
        "side_rule": theme["side_rule"], "side_muted": theme["side_muted"],
        "fb": _CSS_FONTS[theme["font"]],
        "fh": _CSS_FONTS[theme["heading_font"] or theme["font"]],
        "body": _pt_px(m["body"]), "lead": f"{m['lead'] / m['body']:.3f}",
        "small": _pt_px(m["small"]), "chip": _pt_px(m["small"] + 0.2),
        "label": _pt_px(m["small"] - 1), "name": _pt_px(theme["name_size"]),
        "role": _pt_px(m["body"] + 1.5), "h2": _pt_px(m["h2"]),
        "sh2": _pt_px(m["h2"] - 0.5), "gap": _pt_px(m["gap"]),
        "gap2": _pt_px(m["gap"] * 0.45), "para": _pt_px(m["para"]),
        "para7": _pt_px(m["para"] * 0.7),
        "side": _mm_px(m["side_mm"]), "top": _mm_px(m["top_mm"]),
        "bottom": _mm_px(m["bottom_mm"]), "bandtop": _mm_px(15), "bandbot": _mm_px(8),
    }
    css = _HTML_PAGE_CSS
    for name, value in tokens.items():
        css = css.replace(f"@{name}@", str(value))
    return _to_scaled_px(css)


def _h(value) -> str:
    return html.escape(str(value))


def _html_list(items: list[str], extra_class: str = "") -> str:
    classes = f"b {extra_class}".strip()
    body = "".join(f"<li>{_h(item)}</li>" for item in items)
    return f'<ul class="{classes}">{body}</ul>'


def _html_experience(entries: list[dict]) -> str:
    blocks = []
    for entry in entries:
        first, second = _entry_lines(entry)
        dates = _entry_dates(entry)
        top = f'<span class="e-title">{_h(first)}</span>'
        if dates:
            top += f'<span class="e-date">{_h(dates)}</span>'
        block = [f'<div class="entry"><div class="e-top">{top}</div>']
        if second:
            block.append(f'<div class="e-sub">{_h(second)}</div>')
        if entry["responsibilities"]:
            block.append(_html_list(entry["responsibilities"]))
        block.append("</div>")
        blocks.append("".join(block))
    return "".join(blocks)


def _html_body(key: str, document: dict, theme: dict, side: bool) -> str:
    if key == "summary":
        return f"<p>{_h(document['summary'])}</p>"
    if key == "experience":
        return _html_experience(document["experience"])

    items = document[key]
    if side:
        return _html_list(items)
    if key == "languages":
        return f"<p>{_h(' · '.join(items))}</p>"
    if key == "skills":
        style = theme["skills_style"]
        if style == "inline":
            return f"<p>{_h(theme['skills_sep'].join(items))}</p>"
        if style == "chips":
            chips = "".join(f'<span class="chip">{_h(item)}</span>' for item in items)
            return f'<div class="chips">{chips}</div>'
        if style == "columns":
            extra = "cols c3" if theme["skills_cols"] >= 3 else "cols"
            return _html_list(items, extra)
    return _html_list(items)


def _html_section(key: str, document: dict, theme: dict, side: bool = False) -> str:
    body = _html_body(key, document, theme, side)
    title = _h(SECTION_TITLES[key].upper())
    return f'<section class="sec sec-{key}"><h2>{title}</h2>{body}</section>'


def _html_head(document: dict, theme: dict, contact_inline: bool = True) -> str:
    name = _h(_display_name(document, theme) or "Your Name")
    role = f'<div class="role">{_h(document["target_role"])}</div>' if document["target_role"] else ""
    contact = ""
    if contact_inline:
        values = [_h(value) for _, value in _contact_items(document)]
        text = "<i>|</i>".join(values) if values else "Location<i>|</i>Phone<i>|</i>Email"
        contact = f'<div class="contact">{text}</div>'

    classes = ["head"]
    if theme["header"] == "center":
        classes.append("center")
    if theme["band"]:
        classes.append("band")
    elif theme["header_rule"]:
        classes.append(f"rule-{theme['header_rule']}")
    return (
        f'<header class="{" ".join(classes)}"><div class="head-in">'
        f"<h1>{name}</h1>{role}{contact}</div></header>"
    )


def _html_sidebar(document: dict, theme: dict, keys: list[str]) -> str:
    parts = []
    contact = _contact_items(document)
    if contact:
        rows = "".join(
            f"<li><b>{_h(label)}</b><span>{_h(value)}</span></li>" for label, value in contact
        )
        parts.append(f'<section class="sec"><h2>CONTACT</h2><ul class="ct">{rows}</ul></section>')
    parts.extend(_html_section(key, document, theme, side=True) for key in keys)
    return f'<aside class="side-col">{"".join(parts)}</aside>'


def build_cv_html(
    profile: dict,
    cv_data: dict | None = None,
    template: str = DEFAULT_TEMPLATE,
    accent: str | None = None,
) -> str:
    """Render a self-contained HTML preview from the same CV data."""

    document = build_cv_document(profile, cv_data)
    theme = _theme(template, accent)
    side_keys, main_keys = _split_columns(document, theme)

    sections = "".join(_html_section(key, document, theme) for key in main_keys)
    if not sections and not side_keys:
        sections = (
            '<p class="empty-note">Start filling in the form and your CV '
            "preview will appear here.</p>"
        )
    footer = f'<div class="foot"><span>{_h(BRAND_FOOTER)}</span></div>' if BRAND_FOOTER else ""

    classes = f"sheet hs-{theme['heading_style']}"
    if theme["layout"] == "sidebar":
        page = (
            f'<div class="{classes} side">{_html_sidebar(document, theme, side_keys)}'
            f'<div class="main-col">{_html_head(document, theme, contact_inline=False)}'
            f"{sections}{footer}</div></div>"
        )
    else:
        page = (
            f'<div class="{classes}">{_html_head(document, theme)}'
            f'<div class="body">{sections}{footer}</div></div>'
        )

    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        f"<style>{_HTML_FIXED_CSS}{_html_css(theme)}</style></head>"
        f'<body><div class="stage">{page}</div></body></html>'
    )


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _pdf_safe(value) -> str:
    """Keep only characters ReportLab's built-in fonts can draw (Windows-1252)."""

    out = []
    for char in _CONTROL_RE.sub("", str(value)):
        try:
            char.encode("cp1252")
            out.append(char)
        except UnicodeEncodeError:
            base = unicodedata.normalize("NFKD", char).encode("cp1252", "ignore").decode("cp1252")
            out.append(base or "?")
    return "".join(out)


def _t(value) -> str:
    """Text ready to place inside a Paragraph."""

    return escape(_pdf_safe(value))


class _Chips(Flowable):
    """Rounded 'tag' labels that wrap across lines and split across pages."""

    def __init__(self, items, font, size, fill, text_color,
                 pad_x=5.5, pad_y=2.8, gap_x=4.0, gap_y=4.0):
        super().__init__()
        self.items = [_pdf_safe(item) for item in items]
        self.font, self.size = font, size
        self.fill, self.text_color = fill, text_color
        self.pad_x, self.pad_y, self.gap_x, self.gap_y = pad_x, pad_y, gap_x, gap_y
        self.hAlign = "LEFT"
        self.spaceAfter = 2
        self._rows: list[list[tuple[str, float]]] = []

    @property
    def _row_height(self) -> float:
        return self.size + 2 * self.pad_y

    def _layout(self, available: float):
        rows: list[list[tuple[str, float]]] = [[]]
        x = 0.0
        for text in self.items:
            width = stringWidth(text, self.font, self.size) + 2 * self.pad_x
            if width > available:
                while text and stringWidth(text + "…", self.font, self.size) + 2 * self.pad_x > available:
                    text = text[:-1]
                text += "…"
                width = stringWidth(text, self.font, self.size) + 2 * self.pad_x
            if rows[-1] and x + width > available:
                rows.append([])
                x = 0.0
            rows[-1].append((text, width))
            x += width + self.gap_x
        return rows if rows[0] else []

    def wrap(self, available_width, available_height):
        self._rows = self._layout(available_width)
        count = len(self._rows)
        height = count * self._row_height + max(count - 1, 0) * self.gap_y
        self.width, self.height = available_width, height
        return available_width, height

    def split(self, available_width, available_height):
        rows = self._layout(available_width)
        fit = int((available_height + self.gap_y) // (self._row_height + self.gap_y))
        if fit <= 0 or fit >= len(rows):
            return []
        clone = lambda part: _Chips(  # noqa: E731
            [text for row in part for text, _ in row], self.font, self.size,
            self.fill, self.text_color, self.pad_x, self.pad_y, self.gap_x, self.gap_y,
        )
        return [clone(rows[:fit]), clone(rows[fit:])]

    def draw(self):
        canvas = self.canv
        y = self.height - self._row_height
        canvas.setFont(self.font, self.size)
        for row in self._rows:
            x = 0.0
            for text, width in row:
                canvas.setFillColor(self.fill)
                canvas.roundRect(x, y, width, self._row_height, self._row_height / 2, stroke=0, fill=1)
                canvas.setFillColor(self.text_color)
                canvas.drawString(x + self.pad_x, y + self._row_height / 2 - self.size * 0.34, text)
                x += width + self.gap_x
            y -= self._row_height + self.gap_y


def _numbered_canvas(left_text: str, x_left: float, x_right: float, y: float):
    """Canvas that adds a small footer and 'Page n of N' (only when N > 1)."""

    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_pages = []

        def showPage(self):
            self._saved_pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_pages)
            for state in self._saved_pages:
                self.__dict__.update(state)
                self._footer(total)
                super().showPage()
            super().save()

        def _footer(self, total):
            self.saveState()
            self.setFont("Helvetica", 7.5)
            self.setFillColor(HexColor("#8A97A6"))
            if left_text:
                self.drawString(x_left, y, _pdf_safe(left_text))
            if total > 1:
                self.drawRightString(x_right, y, f"Page {self._pageNumber} of {total}")
            self.restoreState()

    return NumberedCanvas


def _pdf_styles(theme: dict) -> dict[str, ParagraphStyle]:
    m = theme["m"]
    fb, fh = theme["font_body"], theme["font_head"]
    accent = HexColor(theme["accent_text"])
    muted, ink = HexColor(theme["muted"]), HexColor(theme["ink"])
    on, side_muted = HexColor(theme["on_accent"]), HexColor(theme["side_muted"])
    band = theme["band"]
    align = TA_CENTER if theme["header"] == "center" else TA_LEFT
    body, lead, small = m["body"], m["lead"], m["small"]
    name_pt = theme["name_size"]

    def style(name, **kw):
        return ParagraphStyle(name, **kw)

    s = {
        "name": style("name", fontName=fh[1], fontSize=name_pt, leading=name_pt * 1.18,
                      textColor=on if band else accent, alignment=align, spaceAfter=1),
        "role": style("role", fontName=fb[1], fontSize=body + 1.5, leading=(body + 1.5) * 1.3,
                      textColor=on if band else muted, alignment=align, spaceAfter=1),
        "contact": style("contact", fontName=fb[0], fontSize=small, leading=small * 1.45,
                         textColor=on if band else muted, alignment=align),
        "h2": style("h2", fontName=fh[1], fontSize=m["h2"], leading=m["h2"] * 1.3,
                    textColor=accent, spaceBefore=m["gap"]),
        "body": style("body", fontName=fb[0], fontSize=body, leading=lead,
                      textColor=ink, spaceAfter=m["para"]),
        "e_title": style("e_title", fontName=fb[1], fontSize=body + 0.4, leading=lead, textColor=ink),
        "e_date": style("e_date", fontName=fb[0], fontSize=small, leading=lead,
                        textColor=muted, alignment=TA_RIGHT),
        "e_sub": style("e_sub", fontName=fb[2], fontSize=body, leading=lead,
                       textColor=muted, spaceAfter=1.5),
        "s_h2": style("s_h2", fontName=fh[1], fontSize=m["h2"] - 0.5, leading=m["h2"] * 1.3,
                      textColor=on, spaceBefore=m["gap"]),
        "s_label": style("s_label", fontName=fb[1], fontSize=small - 1, leading=small,
                         textColor=side_muted),
        "s_text": style("s_text", fontName=fb[0], fontSize=body - 0.3, leading=lead - 0.8,
                        textColor=on, spaceAfter=3),
    }
    s["bullet"] = style("bullet", parent=s["body"], leftIndent=10, bulletIndent=0,
                        bulletFontName=fb[0], bulletFontSize=body, spaceAfter=m["para"] * 0.7)
    s["s_bullet"] = style("s_bullet", parent=s["s_text"], leftIndent=9, bulletIndent=0,
                          bulletFontName=fb[0], bulletFontSize=body - 0.3)
    return s


def _mail_link(label: str, value: str, color: str) -> str:
    if label == "Email":
        target = escape(_pdf_safe(value), {'"': "&quot;"})
        return f'<a href="mailto:{target}" color="{color}">{_t(value)}</a>'
    return _t(value)


def _pdf_header(document: dict, theme: dict, st: dict) -> list:
    flows = [Paragraph(_t(_display_name(document, theme) or "Your Name"), st["name"])]
    if document["target_role"]:
        flows.append(Paragraph(_t(document["target_role"]), st["role"]))
    contact = _contact_items(document)
    if contact:
        color = theme["on_accent"] if theme["band"] else theme["muted"]
        flows.append(Paragraph(
            " | ".join(_mail_link(label, value, color) for label, value in contact),
            st["contact"],
        ))

    accent = HexColor(theme["accent"])
    rule = theme["header_rule"]
    if rule == "thin":
        flows.append(HRFlowable(width="100%", thickness=1, color=accent, spaceBefore=4, spaceAfter=2))
    elif rule == "thick":
        flows.append(HRFlowable(width="100%", thickness=2.2, color=accent, spaceBefore=4, spaceAfter=2))
    elif rule == "double":
        flows.append(HRFlowable(width="100%", thickness=1.8, color=accent, spaceBefore=5, spaceAfter=1.6))
        flows.append(HRFlowable(width="100%", thickness=0.5, color=accent, spaceAfter=2))
    return flows


def _pdf_heading(title: str, theme: dict, st: dict, width: float, side: bool) -> list:
    m = theme["m"]
    if side:
        return [
            Paragraph(_t(title), st["s_h2"]),
            HRFlowable(width="100%", thickness=0.6, color=HexColor(theme["side_rule"]),
                       spaceBefore=1, spaceAfter=4),
        ]

    style = theme["heading_style"]
    if style in ("bar", "filled"):
        accent = HexColor(theme["accent"])
        if style == "bar":
            table = Table([["", Paragraph(_t(title), ParagraphStyle("h2t", parent=st["h2"], spaceBefore=0))]],
                          colWidths=[3.2, width - 3.2], hAlign="LEFT",
                          spaceBefore=m["gap"], spaceAfter=4)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (1, 0), (1, 0), 6), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
        else:
            table = Table([[Paragraph(_t(title), ParagraphStyle("h2t", parent=st["h2"], spaceBefore=0))]],
                          colWidths=[width], hAlign="LEFT", spaceBefore=m["gap"], spaceAfter=4)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), HexColor(theme["tint"])),
                ("LINEBEFORE", (0, 0), (0, 0), 2.5, accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
        return [table]

    if style == "plain":
        return [Paragraph(_t(title), ParagraphStyle("h2p", parent=st["h2"], spaceAfter=3))]

    rule_color = HexColor(theme["accent"] if style == "rule_accent" else "#D8DFE8")
    return [
        Paragraph(_t(title), st["h2"]),
        HRFlowable(width="100%", thickness=0.7, color=rule_color, spaceBefore=1, spaceAfter=4),
    ]


def _pdf_experience(entries: list[dict], theme: dict, st: dict, width: float) -> list:
    m = theme["m"]
    font, small = theme["font_body"][0], m["small"]
    flows: list = []
    for number, entry in enumerate(entries):
        first, second = _entry_lines(entry)
        dates = _entry_dates(entry)
        if dates:
            date_width = min(width * 0.4, stringWidth(_pdf_safe(dates), font, small) + 6)
            header = Table(
                [[Paragraph(_t(first), st["e_title"]), Paragraph(_t(dates), st["e_date"])]],
                colWidths=[width - date_width, date_width], hAlign="LEFT",
            )
            header.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
        else:
            header = Paragraph(_t(first), st["e_title"])

        lead_in = [header]
        if second:
            lead_in.append(Paragraph(_t(second), st["e_sub"]))
        bullets = [Paragraph(_t(item), st["bullet"], bulletText="•") for item in entry["responsibilities"]]

        if number:
            flows.append(Spacer(1, m["gap"] * 0.45))
        # Avoid stranding an entry's title at the bottom of a page.
        flows.append(CondPageBreak(m["lead"] * 4.5))
        flows.extend(lead_in)
        flows.extend(bullets)
    return flows


def _pdf_skills(items: list[str], theme: dict, st: dict, width: float) -> list:
    style = theme["skills_style"]
    if style == "inline":
        return [Paragraph(theme["skills_sep"].join(_t(item) for item in items), st["body"])]
    if style == "chips":
        size = theme["m"]["small"] + 0.2
        return [_Chips(items, theme["font_body"][0], size,
                       HexColor(theme["tint"]), HexColor(theme["accent_text"]))]
    if style == "columns":
        columns = max(1, int(theme["skills_cols"]))
        rows = -(-len(items) // columns)
        data = [
            [
                Paragraph(_t(items[c * rows + r]), st["bullet"], bulletText="•")
                if c * rows + r < len(items) else ""
                for c in range(columns)
            ]
            for r in range(rows)
        ]
        table = Table(data, colWidths=[width / columns] * columns, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ]))
        return [table]
    return [Paragraph(_t(item), st["bullet"], bulletText="•") for item in items]


def _pdf_body(key: str, document: dict, theme: dict, st: dict, width: float, side: bool) -> list:
    if key == "summary":
        return [Paragraph(_t(document["summary"]), st["s_text"] if side else st["body"])]
    if key == "experience":
        return _pdf_experience(document["experience"], theme, st, width)

    items = document[key]
    if side:
        return [Paragraph(_t(item), st["s_bullet"], bulletText="•") for item in items]
    if key == "skills":
        return _pdf_skills(items, theme, st, width)
    if key == "languages":
        return [Paragraph(" · ".join(_t(item) for item in items), st["body"])]
    return [Paragraph(_t(item), st["bullet"], bulletText="•") for item in items]


def _pdf_section(key: str, document: dict, theme: dict, st: dict, width: float, side: bool = False) -> list:
    body = _pdf_body(key, document, theme, st, width, side)
    if not body:
        return []
    head = _pdf_heading(SECTION_TITLES[key].upper(), theme, st, width, side)
    if side:  # the sidebar lives inside a KeepInFrame, which has no page breaks
        return [*head, *body]
    # Do not leave a heading alone at the bottom of a page.
    return [CondPageBreak(theme["m"]["lead"] * 5 + theme["m"]["gap"]), *head, *body]


def _pdf_sidebar(document: dict, theme: dict, st: dict, keys: list[str], width: float) -> list:
    flows: list = []
    contact = _contact_items(document)
    if contact:
        flows += _pdf_heading("CONTACT", theme, st, width, side=True)
        for label, value in contact:
            flows.append(Paragraph(_t(label.upper()), st["s_label"]))
            flows.append(Paragraph(_mail_link(label, value, theme["on_accent"]), st["s_text"]))
    for key in keys:
        flows += _pdf_section(key, document, theme, st, width, side=True)
    return flows


def generate_cv_pdf(
    cv_content,
    pdf_path,
    template: str = DEFAULT_TEMPLATE,
    accent: str | None = None,
) -> None:
    """Render a CV using one of the built-in templates.

    ``cv_content`` is the object returned by ``build_cv_content`` (preferred),
    a structured document from ``build_cv_document``, or plain canonical CV text.
    ``pdf_path`` may be a filesystem path or a writable binary buffer.
    ``accent`` optionally overrides the template colour (``#RRGGBB``).
    """

    document = _coerce_document(cv_content)
    theme = _theme(template, accent)
    st = _pdf_styles(theme)
    m = theme["m"]

    page_w, page_h = A4
    top, bottom = m["top_mm"] * mm, m["bottom_mm"] * mm
    side_margin = m["side_mm"] * mm
    side_keys, main_keys = _split_columns(document, theme)
    no_padding = dict(leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    accent_color = HexColor(theme["accent"])

    def make_frame(fid, x, y, w, h):
        return Frame(x, y, w, h, id=fid, **no_padding)

    if theme["layout"] == "sidebar":
        side_w, side_pad, gap, right = 62 * mm, 7 * mm, 9 * mm, 15 * mm
        main_x = side_w + gap
        main_w = page_w - main_x - right
        frame_h = page_h - top - bottom
        inner_w = side_w - 2 * side_pad

        def paint_side(canvas, _doc):
            canvas.saveState()
            canvas.setFillColor(accent_color)
            canvas.rect(0, 0, side_w, page_h, stroke=0, fill=1)
            canvas.restoreState()

        templates = [
            PageTemplate(id="first", onPage=paint_side, frames=[
                make_frame("side", side_pad, bottom, inner_w, frame_h),
                make_frame("main", main_x, bottom, main_w, frame_h)]),
            PageTemplate(id="later", onPage=paint_side, frames=[
                make_frame("main2", main_x, bottom, main_w, frame_h)]),
        ]
        sidebar = _pdf_sidebar(document, theme, st, side_keys, inner_w)
        story = [KeepInFrame(inner_w, frame_h - 1, sidebar, mode="shrink"),
                 FrameBreak(), NextPageTemplate("later")]
        story += _pdf_header(document, theme, st)
        for key in main_keys:
            story += _pdf_section(key, document, theme, st, main_w)
        footer_left, footer_right = main_x, page_w - right

    else:
        width = page_w - 2 * side_margin
        frame_h = page_h - top - bottom
        footer_left, footer_right = side_margin, page_w - side_margin
        if theme["band"]:
            pad_top, pad_bottom = 15 * mm, 8 * mm
            parts = _pdf_header(document, theme, st)
            parts = [p for p in parts if isinstance(p, Paragraph)]
            heights = [p.wrap(width, page_h)[1] for p in parts]
            band_h = pad_top + sum(heights) + pad_bottom

            def paint_band(canvas, _doc):
                canvas.saveState()
                canvas.setFillColor(accent_color)
                canvas.rect(0, page_h - band_h, page_w, band_h, stroke=0, fill=1)
                y = page_h - pad_top
                for paragraph, height in zip(parts, heights):
                    y -= height
                    paragraph.drawOn(canvas, side_margin, y)
                canvas.restoreState()

            first_h = page_h - band_h - 6 * mm - bottom
            templates = [
                PageTemplate(id="first", onPage=paint_band,
                             frames=[make_frame("first", side_margin, bottom, width, first_h)]),
                PageTemplate(id="later", frames=[make_frame("later", side_margin, bottom, width, frame_h)]),
            ]
            story = [NextPageTemplate("later")]
        else:
            templates = [PageTemplate(id="first", frames=[
                make_frame("main", side_margin, bottom, width, frame_h)])]
            story = _pdf_header(document, theme, st)
        for key in main_keys:
            story += _pdf_section(key, document, theme, st, width)

    target = str(pdf_path) if isinstance(pdf_path, (str, Path)) else pdf_path
    name = document["name"]
    builder = BaseDocTemplate(
        target,
        pagesize=A4,
        pageTemplates=templates,
        title=f"CV - {_pdf_safe(name)}" if name else "Professional CV",
        author=_pdf_safe(name) or "KaziMsaada AI",
        creator="KaziMsaada AI",
    )
    builder.build(story, canvasmaker=_numbered_canvas(BRAND_FOOTER, footer_left, footer_right, 9.5 * mm))


# --------------------------------------------------------------------------
# Saving and listing
# --------------------------------------------------------------------------

def save_cv_bundle(
    profile: dict,
    cv_data: dict | None = None,
    template: str = DEFAULT_TEMPLATE,
    cv_dir: str | Path | None = None,
    accent: str | None = None,
) -> dict:
    """Write text and PDF versions of a CV and return their details."""

    if template not in TEMPLATES:
        template = DEFAULT_TEMPLATE

    directory = Path(cv_dir) if cv_dir is not None else CV_DIR
    directory.mkdir(parents=True, exist_ok=True)

    cv_content = build_cv_content(profile, cv_data)

    profile_id = str(profile.get("profile_id", "unknown"))
    profile_token = "".join(
        character
        if character.isalnum() or character in ("-", "_")
        else "_"
        for character in profile_id
    )[:8] or "unknown"
    filename = (
        f"CV_{profile_token}_{template}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    )

    txt_path = directory / f"{filename}.txt"
    pdf_path = directory / f"{filename}.pdf"

    # Generate the PDF before writing either file so a PDF failure does not
    # leave an orphaned text CV behind. Remove a partial pair if a disk write
    # fails after generation.
    pdf_buffer = io.BytesIO()
    generate_cv_pdf(cv_content, pdf_buffer, template=template, accent=accent)
    pdf_bytes = pdf_buffer.getvalue()

    try:
        txt_path.write_text(str(cv_content), encoding="utf-8")
        pdf_path.write_bytes(pdf_bytes)
    except OSError:
        txt_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)
        raise

    return {
        "filename": filename,
        "template": template,
        "template_name": TEMPLATES[template]["name"],
        "txt_path": txt_path,
        "pdf_path": pdf_path,
        "content": str(cv_content),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def list_saved_cvs(cv_dir: str | Path | None = None) -> list[dict]:
    """List generated PDF CVs, newest first, for real dashboard metrics."""

    directory = Path(cv_dir) if cv_dir is not None else CV_DIR
    if not directory.exists():
        return []

    records = []
    for pdf_path in directory.glob("*.pdf"):
        try:
            stat = pdf_path.stat()
        except OSError:
            continue

        records.append(
            {
                "name": pdf_path.name,
                "path": pdf_path,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "text_path": pdf_path.with_suffix(".txt"),
            }
        )

    records.sort(key=lambda item: item["modified"], reverse=True)
    return records


def count_saved_cvs(cv_dir: str | Path | None = None) -> int:
    return len(list_saved_cvs(cv_dir))
